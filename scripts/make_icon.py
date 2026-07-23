#!/usr/bin/env python3
"""Generate the FIVE HUB app icon: white goop on an ink rounded square.

Writes assets/icon.png (256px, Linux/window icon) and assets/fivehub.ico
(multi-size, Windows shortcuts + taskbar). Same metaball language as the
splash. Requires Pillow.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fivehub.tools.splash import _goop_layer  # noqa: E402

SIZE = 256
INK = (11, 11, 12)

# Metaballs in a 1200x675 space (what _goop_layer scales from) chosen to
# read as one liquid mark at 16px.
ICON_BLOBS = [
    (430, 240, 150), (740, 300, 118), (520, 470, 108), (790, 500, 60),
]


def render():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(SIZE * 0.24)
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius, fill=INK + (255,))

    # _goop_layer thinks in 1200x675; render a square by letterboxing.
    field_w, field_h = SIZE * 2, int(SIZE * 2 * 675 / 1200)
    mask = _goop_layer(field_w, field_h, ICON_BLOBS, threshold=1.15)
    mask = mask.resize((SIZE, int(SIZE * 675 / 1200)))
    white = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    image.paste(white, (0, (SIZE - mask.size[1]) // 2), mask)

    assets = os.path.join(REPO, "assets")
    os.makedirs(assets, exist_ok=True)
    png_path = os.path.join(assets, "icon.png")
    image.save(png_path, "PNG")
    ico_path = os.path.join(assets, "fivehub.ico")
    image.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                (64, 64), (128, 128), (256, 256)])
    return png_path, ico_path


if __name__ == "__main__":
    print(render())
