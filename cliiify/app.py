import os
import re
import select
import shutil
import signal
import sys
import termios
import time
import tty
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from chafa.loader import Loader

from .manifest import Canvas
from .image import (
    REFETCH_MARGIN,
    Rect,
    base_size,
    detail_request,
    fetch_info,
    tile_fresh,
    tile_plan,
    tile_usable,
)
from .render import GLYPH_PIXELS, fetch_image, layout, render
from .viewport import Viewport


# Wait for pan/zoom to settle before requesting a detail region. Just over
# the ~30ms gap between key repeats, so a held key makes one request.
SETTLE_SECONDS = 0.05
# How often to check on tile requests, versus when nothing is outstanding.
BUSY_TICK = 0.02
IDLE_TICK = 0.1

ENTER_ALT = '\x1b[?1049h\x1b[?25l'
LEAVE_ALT = '\x1b[?25h\x1b[?1049l'
KEY_RE = re.compile(rb'\x1b\[[0-9;]*[A-Za-z~]|.', re.DOTALL)

# Key sequence -> (method name, args)
KEYMAP: dict[bytes, tuple[str, tuple]] = {}
for keys, action in [
    ((b'+', b'='), ('zoom', (1,))),
    ((b'-',), ('zoom', (-1,))),
    ((b'\x1b[D',), ('pan', (-1, 0))),
    ((b'\x1b[C',), ('pan', (1, 0))),
    ((b'\x1b[A',), ('pan', (0, -1))),
    ((b'\x1b[B',), ('pan', (0, 1))),
    ((b'\x1b[1;2D',), ('pan', (-3, 0))),
    ((b'\x1b[1;2C',), ('pan', (3, 0))),
    ((b'\x1b[1;2A',), ('pan', (0, -3))),
    ((b'\x1b[1;2B',), ('pan', (0, 3))),
    ((b'0',), ('reset', ())),
    ((b'n', b'\x1b[6~'), ('step', (1,))),
    ((b'p', b'\x1b[5~'), ('step', (-1,))),
    ((b'q', b'\x03'), ('quit', ())),
]:
    for key in keys:
        KEYMAP[key] = action


Region = tuple[float, float, float, float]


@dataclass
class Detail:
    """A sharper image of part of a canvas."""

    index: int
    region: Region
    loader: Loader

    def covers(self, rect: Region) -> bool:
        eps = 1e-6
        r = self.region
        return (
            r[0] <= rect[0] + eps
            and r[1] <= rect[1] + eps
            and r[2] >= rect[2] - eps
            and r[3] >= rect[3] - eps
        )


class Viewer:
    def __init__(self, title: str, canvases: list[Canvas]):
        self.title = title
        self.canvases = canvases
        self.index = 0
        self.view = Viewport()
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.futures: dict[int, Future] = {}
        self.infos: dict[int, Future] = {}
        self.info_seen: set[int] = set()
        # Detail tile on screen: (loader, rect, width in px); and the one in flight.
        self.tile: tuple[Loader, Rect, int] | None = None
        self.pending: tuple[Rect, int, Future] | None = None
        self.want: tuple[Rect, int, str] | None = None
        self.shown: tuple[Loader, Rect] | None = None
        self.visible: Rect = (0, 0, 1, 1)
        self.screen: dict[int, tuple[int, int, str]] = {}
        self.status = ''
        self.full = (1, 1)
        self.size = 1
        self.settle_at = 0.0
        self.running = True
        self.resized = True
        self.dirty = True
        self.shown_ready = False
        self.detail_pool = ThreadPoolExecutor(max_workers=1)
        self.detail: Detail | None = None
        self.detail_future: Future | None = None
        self.detail_request: tuple[int, Region] | None = None
        self.detail_due: float | None = None

    def future(self, index: int) -> Future:
        if index not in self.futures:
            cols, rows = shutil.get_terminal_size()
            info = self.info_future(index)
            self.futures[index] = self.pool.submit(
                self.load_base, self.canvases[index], info, (cols, rows - 1)
            )
        return self.futures[index]

    @staticmethod
    def load_base(canvas: Canvas, info: Future | None, cells: tuple[int, int]) -> Loader:
        """Fetch the whole image, sized to the terminal when the service is known."""
        if info is not None and canvas.service:
            try:
                size = base_size(info.result(), cells)
                return fetch_image(f'{canvas.service}/full/{size},/0/default.jpg')
            except Exception:
                pass
        return fetch_image(canvas.image_url)

    def info_future(self, index: int) -> Future | None:
        service = self.canvases[index].service
        if service is None:
            return None
        if index not in self.infos:
            self.infos[index] = self.pool.submit(fetch_info, service)
        return self.infos[index]

    def plan_detail(self, base, cells) -> None:
        """Pick the tile to draw and, if needed, the tile to request next."""
        self.want = self.shown = None
        canvas = self.canvases[self.index]
        info = self.info_future(self.index)
        if info is None or not info.done() or info.exception():
            return
        full = info.result()
        self.full = full
        rect = self.visible = self.view.rect(*full)
        plan = detail_request(canvas.service, rect, cells, self.view.rect(base.width, base.height)[2])
        if plan is None:
            return
        size = plan[0][-1]
        self.size = size
        if self.tile and tile_usable(self.tile[1], self.tile[2], rect, size):
            self.shown = self.tile[:2]
        if not (self.tile and tile_fresh(self.tile[1], self.tile[2], rect, size, full)):
            self.want = tile_plan(canvas.service, full, rect, size)

    def poll(self) -> None:
        """Collect finished work and start the next tile request."""
        info = self.infos.get(self.index)
        if info and info.done() and self.index not in self.info_seen:
            self.info_seen.add(self.index)
            self.dirty = True
        if self.pending and self.pending[2].done():
            rect, _, fut = self.pending
            self.pending = None
            if not fut.cancelled() and not fut.exception():
                loader, size = fut.result()
                self.tile = (loader, rect, size)
                self.dirty = True
                return  # the plan is stale; the redraw makes a fresh one
        if self.want is None:
            return
        rect, size, url = self.want
        if self.pending and tile_fresh(
            self.pending[0], self.pending[1], self.visible, self.size, self.full
        ):
            return
        # With a tile already on screen, fetch at once; otherwise wait for the
        # view to settle so a burst of key presses makes one request.
        if self.shown is None and time.monotonic() < self.settle_at:
            return
        if self.pending:
            self.pending[2].cancel()
        self.pending = (rect, size, self.pool.submit(lambda: (fetch_image(url), size)))

    def prefetch(self) -> None:
        if self.index + 1 < len(self.canvases):
            self.future(self.index + 1)

    def zoom(self, direction: int) -> None:
        self.view.zoom_in() if direction > 0 else self.view.zoom_out()

    def pan(self, dx: float, dy: float) -> None:
        self.view.pan(dx, dy)

    def reset(self) -> None:
        self.view.reset()

    def step(self, delta: int) -> None:
        new = self.index + delta
        if 0 <= new < len(self.canvases):
            self.index = new
            self.tile = self.pending = None
            self.view.reset()
            self.detail = None
            if self.detail_future:
                self.detail_future.cancel()
            self.shown_ready = False
            self.resized = True

    def on_resize(self, *_) -> None:
        self.resized = True
        self.settle_at = time.monotonic() + SETTLE_SECONDS

    def quit(self) -> None:
        self.running = False

    def draw(self) -> None:
        cols, rows = shutil.get_terminal_size()
        fut = self.future(self.index)
        canvas = self.canvases[self.index]
        prefix = f'[{self.index + 1}/{len(self.canvases)}] {canvas.label}'
        out = ['\x1b[?2026h']
        if self.resized:
            # Terminal contents are unreliable after a resize: start afresh.
            out.append('\x1b[2J')
            self.screen = {}
            self.status = ''
        self.resized = False
        frame: dict[int, tuple[int, int, str]] = {}
        if not fut.done():
            status = f'{prefix} · loading…'
        elif fut.exception():
            status = f'{prefix} · load failed: {fut.exception()}'
        else:
            base = fut.result()
            cells = layout(base, cols, rows - 1, self.view)
            info = self.info_future(self.index)
            full_w = info.result()[0] if info and info.done() and not info.exception() else base.width
            self.view.limit_to(full_w, cols, GLYPH_PIXELS)
            self.plan_detail(base, cells)
            detail = (*self.shown, self.visible) if self.shown else None
            lines, left, top = render(base, cols, rows - 1, self.view, detail=detail)
            for i, line in enumerate(lines):
                frame[top + i + 1] = (left, cells[0], line)
            v = self.view
            status = f'{prefix} · {v.zoom * 100:.0f}% · {v.cx:.2f},{v.cy:.2f}'
            if detail:
                status += ' · detail'
            elif self.want or self.pending:
                status += ' · refining…'
            if not self.shown_ready:
                self.shown_ready = True
                self.prefetch()

        # Only touch rows that changed, and overwrite rather than clear, so
        # terminals without synchronized output don't flash or tear.
        for row in sorted(self.screen.keys() | frame.keys()):
            old, new = self.screen.get(row), frame.get(row)
            if old == new:
                continue
            if new is None:
                out.append(f'\x1b[{row};1H\x1b[2K')
                continue
            left, width, line = new
            if old and old[:2] != new[:2]:
                out.append(f'\x1b[{row};1H\x1b[2K')
            out.append(f'\x1b[{row};{left + 1}H{line}\x1b[0m')
        self.screen = frame
        status = status[:cols].ljust(cols)
        if status != self.status:
            out.append(f'\x1b[{rows};1H\x1b[7m{status}\x1b[0m')
            self.status = status
        out.append('\x1b[?2026l')
        sys.stdout.write(''.join(out))
        sys.stdout.flush()
        self.dirty = False

    def handle(self, data: bytes) -> None:
        for key in KEY_RE.findall(data):
            action = KEYMAP.get(key)
            if action:
                getattr(self, action[0])(*action[1])
                self.dirty = True
                self.settle_at = time.monotonic() + SETTLE_SECONDS

    def run(self) -> None:
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        signal.signal(signal.SIGWINCH, self.on_resize)
        try:
            tty.setraw(fd)
            sys.stdout.write(ENTER_ALT)
            while self.running:
                if self.resized or self.dirty:
                    self.draw()
                    self.dirty = True if not self.future(self.index).done() else False
                self.poll()
                # Short timeout so resizes and finished downloads are noticed.
                busy = self.want or self.pending or not self.future(self.index).done()
                ready, _, _ = select.select([fd], [], [], BUSY_TICK if busy else IDLE_TICK)
                if ready:
                    # Read everything queued so held keys cost one render.
                    self.handle(os.read(fd, 4096))
                self.poll_detail()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            sys.stdout.write(LEAVE_ALT)
            sys.stdout.flush()
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.detail_pool.shutdown(wait=False, cancel_futures=True)


def run(title: str, canvases: list[Canvas]) -> None:
    Viewer(title, canvases).run()
