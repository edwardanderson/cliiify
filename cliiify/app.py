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

from .manifest import Canvas
from chafa.loader import Loader

from .render import fetch_canvas_image, fetch_image, render
from .viewport import Viewport


# chafa resamples to 8x8 pixels per cell, so more detail is never shown.
PIXELS_PER_CELL = 8
MIN_FETCH_WIDTH = 800
# Wait for keys to settle before fetching a sharper region.
DETAIL_DELAY = 0.25
# Fetch this much extra around the visible area so small pans stay covered.
DETAIL_MARGIN = 0.25
# Skip a fetch when the current source is already this close to what's wanted.
DETAIL_TOLERANCE = 0.9
MAX_DETAIL_WIDTH = 4000

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
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.futures: dict[int, Future] = {}
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
            width = max(MIN_FETCH_WIDTH, shutil.get_terminal_size().columns * PIXELS_PER_CELL)
            self.futures[index] = self.pool.submit(
                fetch_canvas_image, self.canvases[index], width
            )
        return self.futures[index]

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
            self.view.reset()
            self.detail = None
            if self.detail_future:
                self.detail_future.cancel()
            self.shown_ready = False
            self.resized = True

    def want_pixels(self) -> float:
        """Source pixels worth showing across the visible width."""
        canvas = self.canvases[self.index]
        x0, _, x1, _ = self.view.frac_rect()
        native = (canvas.width or 0) * (x1 - x0)
        return min(shutil.get_terminal_size().columns * PIXELS_PER_CELL, native)

    def current_source(self) -> tuple[Loader, Region] | None:
        """The sharpest loaded image that covers the visible area."""
        fut = self.future(self.index)
        if not fut.done() or fut.exception():
            return None
        base = fut.result()
        if self.detail and self.detail.index == self.index:
            if self.detail.covers(self.view.frac_rect()):
                return self.detail.loader, self.detail.region
        return base, (0.0, 0.0, 1.0, 1.0)

    def schedule_detail(self) -> None:
        self.detail_due = time.monotonic() + DETAIL_DELAY

    def request_detail(self) -> None:
        canvas = self.canvases[self.index]
        source = self.current_source()
        if not canvas.can_fetch_regions or source is None:
            return
        loader, region = source
        x0, y0, x1, y1 = self.view.frac_rect()
        # Visible source pixels the current image provides across the view.
        have = loader.width * (x1 - x0) / (region[2] - region[0])
        want = self.want_pixels()
        if have >= want * DETAIL_TOLERANCE:
            return
        mx, my = (x1 - x0) * DETAIL_MARGIN, (y1 - y0) * DETAIL_MARGIN
        target = (
            max(0.0, x0 - mx),
            max(0.0, y0 - my),
            min(1.0, x1 + mx),
            min(1.0, y1 + my),
        )
        width = round(want * (target[2] - target[0]) / (x1 - x0))
        width = min(width, MAX_DETAIL_WIDTH)
        if self.detail_future:
            self.detail_future.cancel()
        self.detail_request = (self.index, target)
        self.detail_future = self.detail_pool.submit(
            fetch_image, canvas.region_url(target, width)
        )

    def poll_detail(self) -> None:
        if self.detail_due is not None and time.monotonic() >= self.detail_due:
            self.detail_due = None
            self.request_detail()
        fut = self.detail_future
        if fut is None or not fut.done():
            return
        self.detail_future = None
        request, self.detail_request = self.detail_request, None
        if fut.cancelled() or fut.exception() or request is None:
            return
        # Discard results for a canvas the user has already left.
        if request[0] == self.index:
            self.detail = Detail(request[0], request[1], fut.result())
            self.dirty = True

    def on_resize(self, *_) -> None:
        self.resized = True
        self.schedule_detail()

    def quit(self) -> None:
        self.running = False

    def draw(self) -> None:
        cols, rows = shutil.get_terminal_size()
        fut = self.future(self.index)
        canvas = self.canvases[self.index]
        prefix = f'[{self.index + 1}/{len(self.canvases)}] {canvas.label}'
        out = ['\x1b[?2026h']
        if self.resized:
            # The old contents may be the wrong shape after a resize.
            out.append('\x1b[2J')
            self.resized = False
        if not fut.done():
            status = f'{prefix} · loading…'
        elif fut.exception():
            status = f'{prefix} · load failed: {fut.exception()}'
        else:
            base = fut.result()
            loader, region = self.current_source() or (base, (0.0, 0.0, 1.0, 1.0))
            lines, left, top = render(
                loader,
                cols,
                rows - 1,
                self.view,
                region=region,
                aspect=base.width / base.height,
            )
            # Overwrite rows in place rather than clearing the screen first, so a
            # terminal without synchronized updates never shows a blank frame.
            image_rows = {top + i: line for i, line in enumerate(lines)}
            body = ''.join(
                f'\x1b[{r + 1};1H\x1b[0m'
                + (
                    f'{" " * left}{image_rows[r]}\x1b[0m\x1b[K'
                    if r in image_rows
                    else '\x1b[2K'
                )
                for r in range(rows - 1)
            )
            v = self.view
            status = f'{prefix} · {v.zoom * 100:.0f}% · {v.cx:.2f},{v.cy:.2f}'
            out.append(body)
            if not self.shown_ready:
                self.shown_ready = True
                self.prefetch()

        status = status[:cols].ljust(cols)
        out.append(f'\x1b[{rows};1H\x1b[7m{status}\x1b[0m\x1b[?2026l')
        sys.stdout.write(''.join(out))
        sys.stdout.flush()
        self.dirty = False

    def handle(self, data: bytes) -> None:
        for key in KEY_RE.findall(data):
            action = KEYMAP.get(key)
            if action:
                getattr(self, action[0])(*action[1])
                self.dirty = True
                self.schedule_detail()

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
                # Short timeout so resizes and finished downloads are noticed.
                ready, _, _ = select.select([fd], [], [], 0.05)
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
