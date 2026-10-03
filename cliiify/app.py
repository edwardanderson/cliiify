import os
import re
import select
import shutil
import signal
import sys
import termios
import tty
from concurrent.futures import Future, ThreadPoolExecutor

from .manifest import Canvas
from .render import fetch_image, render
from .viewport import Viewport


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

    def future(self, index: int) -> Future:
        if index not in self.futures:
            self.futures[index] = self.pool.submit(
                fetch_image, self.canvases[index].image_url
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
            self.shown_ready = False
            self.resized = True

    def quit(self) -> None:
        self.running = False

    def draw(self) -> None:
        cols, rows = shutil.get_terminal_size()
        fut = self.future(self.index)
        canvas = self.canvases[self.index]
        prefix = f'[{self.index + 1}/{len(self.canvases)}] {canvas.label}'
        out = ['\x1b[?2026h']
        self.resized = False
        if not fut.done():
            status = f'{prefix} · loading…'
        elif fut.exception():
            status = f'{prefix} · load failed: {fut.exception()}'
        else:
            lines, left, top = render(fut.result(), cols, rows - 1, self.view)
            body = ''.join(
                f'\x1b[{top + i + 1};{left + 1}H{line}\x1b[0m'
                for i, line in enumerate(lines)
            )
            v = self.view
            status = f'{prefix} · {v.zoom * 100:.0f}% · {v.cx:.2f},{v.cy:.2f}'
            out.append(f'\x1b[2J{body}')
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

    def run(self) -> None:
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        signal.signal(signal.SIGWINCH, lambda *_: setattr(self, 'resized', True))
        try:
            tty.setraw(fd)
            sys.stdout.write(ENTER_ALT)
            while self.running:
                if self.resized or self.dirty:
                    self.draw()
                    self.dirty = True if not self.future(self.index).done() else False
                # Short timeout so resizes and finished downloads are noticed.
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    # Read everything queued so held keys cost one render.
                    self.handle(os.read(fd, 4096))
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            sys.stdout.write(LEAVE_ALT)
            sys.stdout.flush()
            self.pool.shutdown(wait=False, cancel_futures=True)


def run(title: str, canvases: list[Canvas]) -> None:
    Viewer(title, canvases).run()
