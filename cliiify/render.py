import ctypes
import tempfile
import urllib.request
from pathlib import Path

import chafa
from chafa.loader import Loader

from .manifest import Canvas
from .viewport import Viewport


def fetch_image(url: str) -> Loader:
    """Load an image from a URL or local path."""
    if Path(url).exists():
        return Loader(url)
    with tempfile.NamedTemporaryFile(suffix=Path(url).suffix or '.img') as tmp:
        with urllib.request.urlopen(url, timeout=30) as resp:
            tmp.write(resp.read())
        tmp.flush()
        loader = Loader(tmp.name)
        loader.get_pixels()
    return loader


def fetch_canvas_image(canvas: Canvas, width: int) -> Loader:
    """Fetch a canvas image scaled to width, falling back to the original URL."""
    url = canvas.url_for(width)
    try:
        return fetch_image(url)
    except Exception:
        if url == canvas.image_url:
            raise
        return fetch_image(canvas.image_url)


def render(
    loader: Loader,
    width: int,
    height: int,
    view: Viewport,
    cell_ratio: float = 0.5,
    region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    aspect: float | None = None,
) -> tuple[list[str], int, int]:
    """Render the view into a width x height cell area.

    cell_ratio is a terminal cell's width divided by its height. If the loader
    holds only a region of the full image (fractions), pass it as region along
    with the full image's aspect ratio.

    Returns (lines, left, top): the image fills the area except where the
    visible window is larger than the image, in which case it is centred.
    """
    width, height = max(1, width), max(1, height)
    term_aspect = width * cell_ratio / height
    img_aspect = aspect or loader.width / loader.height
    view.set_fit(max(1.0, term_aspect / img_aspect), max(1.0, img_aspect / term_aspect))
    ex, ey = view.extent()
    cells_w = max(1, round(width * min(1.0, ex) / ex))
    cells_h = max(1, round(height * min(1.0, ey) / ey))
    x, y, w, h = view.rect(loader.width, loader.height, region)
    pixels = loader.get_pixels()
    offset = y * loader.rowstride + x * loader.channels
    window = (ctypes.c_ubyte * (len(pixels) - offset)).from_buffer(pixels, offset)

    config = chafa.CanvasConfig()
    config.width, config.height = cells_w, cells_h
    # Restrict to block glyphs: box-drawing/diagonal symbols have inconsistent
    # widths across fonts, which scrambles line art and text.
    symbols = chafa.SymbolMap()
    symbols.add_by_tags(
        chafa.SymbolTags.CHAFA_SYMBOL_TAG_SPACE
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_SOLID
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_BLOCK
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_HALF
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_QUAD  # pyright: ignore[reportArgumentType]
    )
    config.set_symbol_map(symbols)
    canvas = chafa.Canvas(config)
    canvas.draw_all_pixels(loader.pixel_type, window, w, h, loader.rowstride)
    lines = canvas.print(fallback=True).decode().split('\n')
    return lines, (width - cells_w) // 2, (height - cells_h) // 2
