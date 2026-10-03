import ctypes
import re
import tempfile
import urllib.request
from pathlib import Path

import chafa
from rich.color import Color
from rich.style import Style
from rich.text import Span, Text
from chafa.loader import Loader

from .viewport import Viewport


def fetch_image(url: str) -> Loader:
    """Load an image from a URL or local path."""
    if Path(url).exists():
        return Loader(url)
    with tempfile.NamedTemporaryFile(suffix=Path(url).suffix or ".img") as tmp:
        with urllib.request.urlopen(url, timeout=30) as resp:
            tmp.write(resp.read())
        tmp.flush()
        # Pixels are decoded eagerly, so the file can go once the loader exists.
        loader = Loader(tmp.name)
        loader.get_pixels()
    return loader


def render(loader: Loader, width: int, height: int, view: Viewport) -> str:
    x, y, w, h = view.rect(loader.width, loader.height)
    pixels = loader.get_pixels()
    offset = y * loader.rowstride + x * loader.channels
    window = (ctypes.c_ubyte * (len(pixels) - offset)).from_buffer(pixels, offset)

    config = chafa.CanvasConfig()
    config.width, config.height = max(1, width), max(1, height)
    # Restrict to block glyphs: box-drawing/diagonal symbols have inconsistent
    # widths across fonts, which scrambles line art and text.
    symbols = chafa.SymbolMap()
    symbols.add_by_tags(
        chafa.SymbolTags.CHAFA_SYMBOL_TAG_SPACE
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_SOLID
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_BLOCK
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_HALF
        | chafa.SymbolTags.CHAFA_SYMBOL_TAG_QUAD
    )
    config.set_symbol_map(symbols)
    config.calc_canvas_geometry(w, h, 0.5)
    canvas = chafa.Canvas(config)
    canvas.draw_all_pixels(loader.pixel_type, window, w, h, loader.rowstride)
    return canvas.print(fallback=True).decode()


_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def to_text(ansi: str) -> Text:
    """Convert chafa's truecolor SGR output to Text (much faster than Text.from_ansi)."""
    styles: dict[tuple, Style] = {}
    parts: list[str] = []
    spans: list[Span] = []
    key: tuple = ()
    pos = 0
    length = 0

    def emit(chunk: str) -> None:
        nonlocal length
        if not chunk:
            return
        if key:
            style = styles.get(key)
            if style is None:
                style = styles[key] = _style(key)
            spans.append(Span(length, length + len(chunk), style))
        parts.append(chunk)
        length += len(chunk)

    for m in _SGR.finditer(ansi):
        emit(ansi[pos : m.start()])
        pos = m.end()
        key = tuple(n for n in map(int, filter(None, m.group(1).split(";")))) 
        if key == (0,):
            key = ()
    emit(ansi[pos:])
    return Text("".join(parts), spans=spans, no_wrap=True, overflow="crop")


def _style(nums: tuple) -> Style:
    fg = bg = None
    i = 0
    while i < len(nums):
        if nums[i] in (38, 48) and nums[i + 1 : i + 2] == (2,):
            color = Color.from_rgb(*nums[i + 2 : i + 5])
            if nums[i] == 38:
                fg = color
            else:
                bg = color
            i += 5
        else:
            i += 1
    return Style(color=fg, bgcolor=bg)
