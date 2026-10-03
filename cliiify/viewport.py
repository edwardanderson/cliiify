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
    # Size of the whole-image view as a fraction of the image (>1 means letterboxed).
    fx: float = 1.0
    fy: float = 1.0

    def set_fit(self, fx: float, fy: float) -> None:
        self.fx, self.fy = fx, fy
        self._clamp()

    def extent(self) -> tuple[float, float]:
        """Visible window as a fraction of the image; may exceed 1 when letterboxed."""
        return self.fx / self.zoom, self.fy / self.zoom

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
        ex, ey = self.extent()
        self.cx += dx * PAN_STEP * ex
        self.cy += dy * PAN_STEP * ey
        self._clamp()

    def _clamp(self) -> None:
        ex, ey = self.extent()
        self.cx = 0.5 if ex >= 1 else min(1 - ex / 2, max(ex / 2, self.cx))
        self.cy = 0.5 if ey >= 1 else min(1 - ey / 2, max(ey / 2, self.cy))

    def rect(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the visible part of the image in pixels."""
        ex, ey = self.extent()
        w = max(1, round(img_w * min(1.0, ex)))
        h = max(1, round(img_h * min(1.0, ey)))
        x = min(img_w - w, max(0, round(self.cx * img_w - w / 2)))
        y = min(img_h - h, max(0, round(self.cy * img_h - h / 2)))
        return x, y, w, h
