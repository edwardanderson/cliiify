from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static

from .manifest import Canvas
from .render import fetch_image, render, to_text
from .viewport import Viewport


class CliiifApp(App):
    BINDINGS = [
        Binding("plus,equals_sign", "zoom_in", "Zoom in"),
        Binding("minus", "zoom_out", "Zoom out"),
        Binding("left,h", "pan(-1,0)", "Pan", show=False),
        Binding("right,l", "pan(1,0)", "Pan", show=False),
        Binding("up,k", "pan(0,-1)", "Pan", show=False),
        Binding("down,j", "pan(0,1)", "Pan", show=False),
        Binding("shift+left,H", "pan(-3,0)", "Fast pan", show=False),
        Binding("shift+right,L", "pan(3,0)", "Fast pan", show=False),
        Binding("shift+up,K", "pan(0,-3)", "Fast pan", show=False),
        Binding("shift+down,J", "pan(0,3)", "Fast pan", show=False),
        Binding("0", "reset", "Reset"),
        Binding("n,pagedown", "step(1)", "Next"),
        Binding("p,pageup", "step(-1)", "Prev"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = "#image { width: 1fr; height: 1fr; content-align: center middle; }"

    def __init__(self, title: str, canvases: list[Canvas]):
        super().__init__()
        self.title = title
        self.canvases = canvases
        self.index = 0
        self.view = Viewport()
        self.loaders: dict[int, object] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="image")
        yield Footer()

    def on_mount(self) -> None:
        self.show_canvas()

    def on_resize(self) -> None:
        self.refresh_image()

    @work(thread=True, exclusive=True)
    def show_canvas(self) -> None:
        canvas = self.canvases[self.index]
        self.call_from_thread(self.set_status, "loading…")
        if self.index not in self.loaders:
            try:
                self.loaders[self.index] = fetch_image(canvas.image_url)
            except Exception as exc:
                self.call_from_thread(self.notify, f"Load failed: {exc}", severity="error")
                return
        self.call_from_thread(self.refresh_image)

    def set_status(self, extra: str) -> None:
        canvas = self.canvases[self.index]
        self.sub_title = (
            f"[{self.index + 1}/{len(self.canvases)}] {canvas.label} · {extra}"
        )

    def refresh_image(self) -> None:
        loader = self.loaders.get(self.index)
        widget = self.query_one("#image", Static)
        if loader is None or widget.size.width == 0:
            return
        size = widget.size
        try:
            ansi = render(loader, size.width, size.height, self.view)
        except Exception as exc:
            self.notify(f"Render failed: {exc}", severity="error")
            return
        widget.update(to_text(ansi))
        v = self.view
        self.set_status(f"{v.zoom * 100:.0f}% · {v.cx:.2f},{v.cy:.2f}")

    def action_zoom_in(self) -> None:
        self.view.zoom_in()
        self.refresh_image()

    def action_zoom_out(self) -> None:
        self.view.zoom_out()
        self.refresh_image()

    def action_pan(self, dx: float, dy: float) -> None:
        self.view.pan(dx, dy)
        self.refresh_image()

    def action_reset(self) -> None:
        self.view.reset()
        self.refresh_image()

    def action_step(self, delta: int) -> None:
        new = self.index + delta
        if 0 <= new < len(self.canvases):
            self.index = new
            self.view.reset()
            self.show_canvas()
