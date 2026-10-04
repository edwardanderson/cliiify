import ctypes
import tempfile
from pathlib import Path

import chafa
from chafa.loader import Loader

from .net import urlopen
from .viewport import Viewport


# Pixels per terminal cell, horizontally, with the block glyphs used below
# (quadrants are 2x2 per cell).
GLYPH_PIXELS = 2


def fetch_image(url: str) -> Loader:
    """Load an image from a URL or local path."""
    if Path(url).exists():
        return Loader(url)
    with tempfile.NamedTemporaryFile(suffix=Path(url).suffix or '.img') as tmp:
        with urlopen(url, timeout=30) as resp:
            tmp.write(resp.read())
        tmp.flush()
        loader = Loader(tmp.name)
        loader.get_pixels()
    return loader


def layout(
    loader: Loader, width: int, height: int, view: Viewport, cell_ratio: float = 0.5
) -> tuple[int, int]:
    """Fit the viewport to the area and return the cells the image occupies."""
    width, height = max(1, width), max(1, height)
    term_aspect = width * cell_ratio / height
    img_aspect = loader.width / loader.height
    view.set_fit(max(1.0, term_aspect / img_aspect), max(1.0, img_aspect / term_aspect))
    ex, ey = view.extent()
    return (
        max(1, round(width * min(1.0, ex) / ex)),
        max(1, round(height * min(1.0, ey) / ey)),
    )


def render(
    loader: Loader,
    width: int,
    height: int,
    view: Viewport,
    cell_ratio: float = 0.5,
    detail: tuple[Loader, tuple[int, int, int, int], tuple[int, int, int, int]] | None = None,
) -> tuple[list[str], int, int]:
    """Render the view into a width x height cell area.

    cell_ratio is a terminal cell's width divided by its height.

    Returns (lines, left, top): the image fills the area except where the
    visible window is larger than the image, in which case it is centred.

    detail, if given, is (tile, tile_rect, visible_rect): a higher-resolution
    image of tile_rect (full-image pixels) containing visible_rect, which is
    cropped from it instead of from loader.
    """
    width, height = max(1, width), max(1, height)
    cells_w, cells_h = layout(loader, width, height, view, cell_ratio)
    if detail is not None:
        source, (tx, ty, tw, th), (vx, vy, vw, vh) = detail
        sx, sy = source.width / tw, source.height / th
        x = min(source.width - 1, max(0, round((vx - tx) * sx)))
        y = min(source.height - 1, max(0, round((vy - ty) * sy)))
        w = max(1, min(source.width - x, round(vw * sx)))
        h = max(1, min(source.height - y, round(vh * sy)))
    else:
        source = loader
        x, y, w, h = view.rect(loader.width, loader.height)
    pixels = source.get_pixels()
    offset = y * source.rowstride + x * source.channels
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
    canvas.draw_all_pixels(source.pixel_type, window, w, h, source.rowstride)
    lines = canvas.print(fallback=True).decode().split('\n')
    return lines, (width - cells_w) // 2, (height - cells_h) // 2
