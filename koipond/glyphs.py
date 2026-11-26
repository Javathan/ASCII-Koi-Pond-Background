"""Glyph atlas construction.

Every frame is composed from a fixed set of pre-rendered character bitmaps.
Rendering a frame is then reduced to an array lookup followed by a color
multiply, which keeps the renderer fast enough for long 4K loops.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Ordered from empty to dense. The index into this ramp is driven by a
# per-cell luminance value in the range [0, 1].
RAMP = " .,:;-~=+*ox#%@"

_FONT_CANDIDATES = {
    "win32": [
        "CascadiaMono.ttf",
        "consola.ttf",
        "lucon.ttf",
        "cour.ttf",
    ],
    "darwin": [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
    ],
    "linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ],
}


def _system_font_dirs() -> list[Path]:
    if sys.platform == "win32":
        root = Path(os.environ.get("WINDIR", "C:/Windows"))
        return [root / "Fonts"]
    return []


def find_monospace_font() -> str | None:
    """Return the path of a monospace TrueType font available on this system."""
    key = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    for candidate in _FONT_CANDIDATES[key]:
        path = Path(candidate)
        if path.is_absolute() and path.exists():
            return str(path)
        for directory in _system_font_dirs():
            if (directory / candidate).exists():
                return str(directory / candidate)
    return None


def build_atlas(cell_w: int, cell_h: int, font_path: str | None = None, chars: str = RAMP) -> np.ndarray:
    """Render ``chars`` into a float32 array of shape (len(chars), cell_h, cell_w).

    Values are coverage in the range [0, 1].
    """
    font_path = font_path or find_monospace_font()
    size = max(6, int(round(cell_h * 0.95)))
    if font_path:
        font = ImageFont.truetype(font_path, size)
    else:
        font = ImageFont.load_default(size=size)

    # Shrink the font until the widest glyph fits inside the cell.
    while size > 6:
        widest = max(font.getbbox(c)[2] - font.getbbox(c)[0] for c in chars if c != " ")
        if widest <= cell_w + 1:
            break
        size -= 1
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)

    atlas = np.zeros((len(chars), cell_h, cell_w), dtype=np.float32)
    for i, ch in enumerate(chars):
        if ch == " ":
            continue
        img = Image.new("L", (cell_w, cell_h), 0)
        ImageDraw.Draw(img).text((cell_w / 2, cell_h / 2), ch, fill=255, font=font, anchor="mm")
        atlas[i] = np.asarray(img, dtype=np.float32) / 255.0
    return atlas
