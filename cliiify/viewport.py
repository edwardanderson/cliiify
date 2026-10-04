from dataclasses import dataclass


MIN_ZOOM = 1.0
# Absolute ceiling; the usable maximum is lower, see limit_to.
MAX_ZOOM = 256.0
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
    max_zoom: float = MAX_ZOOM

    def set_fit(self, fx: float, fy: float) -> None:
        self.fx, self.fy = fx, fy
        self._clamp()

    def limit_to(self, img_w: int, cols: int, pixels_per_cell: float) -> None:
        """Stop zooming once one source pixel fills one terminal pixel.

        Call after set_fit. Further zoom would only enlarge pixels.
        """
        self.max_zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.fx * img_w / (cols * pixels_per_cell)))
        if self.zoom > self.max_zoom:
            self.zoom_by(1.0)

    def extent(self) -> tuple[float, float]:
        """Visible window as a fraction of the image; may exceed 1 when letterboxed."""
        return self.fx / self.zoom, self.fy / self.zoom

    def reset(self) -> None:
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5

    def zoom_by(self, factor: float) -> None:
        self.zoom = min(self.max_zoom, max(MIN_ZOOM, self.zoom * factor))
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

    def frac_rect(self) -> tuple[float, float, float, float]:
        """Visible part of the image as fractions: (x0, y0, x1, y1)."""
        ex, ey = self.extent()
        fw, fh = min(1.0, ex), min(1.0, ey)
        x0 = min(1 - fw, max(0.0, self.cx - fw / 2))
        y0 = min(1 - fh, max(0.0, self.cy - fh / 2))
        return x0, y0, x0 + fw, y0 + fh

    def rect(
        self,
        img_w: int,
        img_h: int,
        region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the visible part in pixels.

        The image may cover only a region of the full image, given as fractions.
        """
        x0, y0, x1, y1 = self.frac_rect()
        rx0, ry0, rx1, ry1 = region
        sx, sy = img_w / (rx1 - rx0), img_h / (ry1 - ry0)
        w = min(img_w, max(1, round((x1 - x0) * sx)))
        h = min(img_h, max(1, round((y1 - y0) * sy)))
        x = min(img_w - w, max(0, round((x0 - rx0) * sx)))
        y = min(img_h - h, max(0, round((y0 - ry0) * sy)))
        return x, y, w, h
