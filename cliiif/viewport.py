from dataclasses import dataclass

MIN_ZOOM = 1.0
MAX_ZOOM = 32.0
ZOOM_STEP = 1.25
PAN_STEP = 0.1


@dataclass
class Viewport:
    """Zoom and centre, with the centre as a fraction (0-1) of the image."""

    zoom: float = 1.0
    cx: float = 0.5
    cy: float = 0.5

    def reset(self) -> None:
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5

    def zoom_by(self, factor: float) -> None:
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * factor))
        self._clamp()

    def zoom_in(self) -> None:
        self.zoom_by(ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom_by(1 / ZOOM_STEP)

    def pan(self, dx: float, dy: float) -> None:
        """Pan by a multiple of the visible extent (1.0 = one full viewport)."""
        self.cx += dx * PAN_STEP / self.zoom
        self.cy += dy * PAN_STEP / self.zoom
        self._clamp()

    def _clamp(self) -> None:
        half = 0.5 / self.zoom
        self.cx = min(1 - half, max(half, self.cx))
        self.cy = min(1 - half, max(half, self.cy))

    def rect(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the visible source region in pixels."""
        w = max(1, round(img_w / self.zoom))
        h = max(1, round(img_h / self.zoom))
        x = min(img_w - w, max(0, round(self.cx * img_w - w / 2)))
        y = min(img_h - h, max(0, round(self.cy * img_h - h / 2)))
        return x, y, w, h
