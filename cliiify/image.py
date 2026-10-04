import json
import re
from pathlib import Path

from .manifest import Canvas, IMAGE_WIDTH
from .net import urlopen


# A trailing /{region}/{size}/{rotation}/{quality}.{format} means the user
# passed an image request rather than an image identifier.
IMAGE_REQUEST_RE = re.compile(r'/[^/]+/[^/]+/!?\d+(?:\.\d+)?/[^/.]+\.[A-Za-z0-9]+$')


def load_image(source: str) -> tuple[str, list[Canvas]]:
    """Load a single, standalone IIIF image (no manifest).

    source is a IIIF Image API base URI (the image identifier, e.g.
    https://example.org/iiif/abc); a trailing /info.json is tolerated. The
    viewer chooses region and size itself.
    """
    service = source.split('?')[0].rstrip('/')
    service = service.removesuffix('/info.json').rstrip('/')
    if IMAGE_REQUEST_RE.search(service):
        raise ValueError(
            'expected an image identifier URL without region/size/rotation/quality '
            f'parameters, e.g. {IMAGE_REQUEST_RE.sub("", service)}'
        )
    title = Path(service).stem or service
    # Fallback used only if info.json can't be read.
    url = f'{service}/full/{IMAGE_WIDTH},/0/default.jpg'
    return title, [Canvas(title, url, service)]


# Source pixels requested per terminal cell. Block glyphs resolve 2x4 pixels
# per cell, so this oversamples a little for sharper downscaling.
PIXELS_PER_CELL = (4, 8)


def fetch_info(service: str) -> tuple[int, int]:
    """Return (width, height) of the full image from its info.json."""
    with urlopen(f'{service}/info.json', timeout=30) as resp:
        info = json.load(resp)
    return int(info['width']), int(info['height'])


def detail_request(
    service: str,
    rect: tuple[int, int, int, int],
    cells: tuple[int, int],
    base_width: int,
) -> tuple[tuple, str] | None:
    """Plan a region request for the visible rect (source pixels).

    Returns (cache key, url), or None when the already-loaded base image
    (whose crop of the region is base_width pixels wide) is as sharp as the
    terminal can show.
    """
    x, y, w, h = rect
    size = min(w, cells[0] * PIXELS_PER_CELL[0], round(cells[1] * PIXELS_PER_CELL[1] * w / h))
    size = max(1, size)
    if base_width >= size:
        return None
    url = f'{service}/{x},{y},{w},{h}/{size},/0/default.jpg'
    return (x, y, w, h, size), url


def base_size(full: tuple[int, int], cells: tuple[int, int]) -> int:
    """Width in pixels for a whole-image request that fills the terminal."""
    full_w, full_h = full
    w = min(cells[0] * PIXELS_PER_CELL[0], cells[1] * PIXELS_PER_CELL[1] * full_w / full_h)
    return max(1, min(full_w, round(w)))


# A detail tile covers the visible region plus this fraction of it on each
# side, so ordinary panning stays inside already-downloaded pixels.
TILE_PADDING = 0.75
# Request a replacement tile once the view comes within this fraction of the
# tile edge, so it normally arrives before the edge is reached.
REFETCH_MARGIN = 0.3
# Tiles are requested this much denser than needed, so they stay sharp enough
# for a few zoom steps while the next tile is fetched.
OVERSAMPLE = 1.5
# A tile may be this much softer than ideal before it is replaced.
MIN_SHARPNESS = 0.75

Rect = tuple[int, int, int, int]


def covers(
    tile: Rect, rect: Rect, margin: float = 0.0, full: tuple[int, int] | None = None
) -> bool:
    """Whether tile contains rect grown by margin (a fraction of rect's size).

    With full given, the grown rect is clamped to the image, since a tile
    can't extend past the image edge.
    """
    x, y, w, h = rect
    mx, my = round(w * margin), round(h * margin)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if full:
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(full[0], x1), min(full[1], y1)
    tx, ty, tw, th = tile
    return tx <= x0 and ty <= y0 and tx + tw >= x1 and ty + th >= y1


def tile_plan(service: str, full: tuple[int, int], rect: Rect, size: int) -> tuple[Rect, int, str]:
    """Plan a padded tile around rect, at the pixel density implied by size
    (the width in pixels wanted for rect itself)."""
    x, y, w, h = rect
    px, py = round(w * TILE_PADDING), round(h * TILE_PADDING)
    x0, y0 = max(0, x - px), max(0, y - py)
    x1, y1 = min(full[0], x + w + px), min(full[1], y + h + py)
    tile = (x0, y0, x1 - x0, y1 - y0)
    # Never ask for more pixels than the source has.
    tile_size = max(1, min(tile[2], round(size * OVERSAMPLE * tile[2] / w)))
    return tile, tile_size, f'{service}/{x0},{y0},{tile[2]},{tile[3]}/{tile_size},/0/default.jpg'


def tile_usable(tile: Rect, tile_size: int, rect: Rect, size: int) -> bool:
    """Whether a tile contains rect and is sharp enough for the wanted size."""
    return covers(tile, rect) and tile_size / tile[2] >= MIN_SHARPNESS * size / rect[2]


def tile_fresh(
    tile: Rect, tile_size: int, rect: Rect, size: int, full: tuple[int, int]
) -> bool:
    """Whether a tile is good for the view with room to spare: it keeps the
    view clear of its edges and is at least as dense as wanted. Once it isn't,
    the next tile is requested, while this one (if still usable) stays on screen."""
    return covers(tile, rect, REFETCH_MARGIN, full) and tile_size / tile[2] >= size / rect[2]
