"""Generates the Sightware brand icon (multi-size .ico + 256px PNG).

Design: dark-navy rounded tile with a subtle vertical gradient, hairline
border, and a bold angular red V (VALORANT palette: #FF4655 on #0F1923).

Run:  python tools/make_icon.py   (requires Pillow)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = 256  # master canvas

NAVY_TOP = (23, 36, 47)     # #17242F
NAVY_BOT = (11, 19, 27)     # #0B141B
BORDER = (42, 56, 68)       # #2A3844
RED = (255, 70, 85)         # #FF4655
RED_DEEP = (198, 44, 58)    # #C62C3A


def rounded_gradient() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        c = tuple(round(a + (b - a) * t) for a, b in
                  zip(NAVY_TOP, NAVY_BOT)) + (255,)
        gd.line([(0, y), (S, y)], fill=c)
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([2, 2, S - 3, S - 3], radius=58, fill=255)
    img.paste(grad, (0, 0), mask)
    # hairline border following the rounded tile
    od = ImageDraw.Draw(img)
    od.rounded_rectangle([2, 2, S - 3, S - 3], radius=58, outline=BORDER,
                         width=2)
    return img


def draw_v(img: Image.Image) -> None:
    """Bold angular V with a two-tone face for depth."""
    v = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    vd = ImageDraw.Draw(v)
    light = [(50, 62), (98, 62), (128, 146), (128, 198), (104, 198)]  # left half
    dark = [(204, 62), (206, 62), (152, 198), (128, 198), (128, 146), (158, 62)]
    vd.polygon(light, fill=RED + (255,))
    vd.polygon([(50, 62), (98, 62), (128, 146), (158, 62), (206, 62),
                (152, 198), (104, 198)], fill=RED + (255,))
    # darker right face: overlap of the right arm polygon
    vd.polygon(dark, fill=RED_DEEP + (255,))
    # re-lighten the left arm precisely
    vd.polygon([(50, 62), (98, 62), (128, 146), (104, 198), (128, 198)],
               fill=RED + (255,))
    img.alpha_composite(v)


def main() -> None:
    img = rounded_gradient()
    draw_v(img)

    png_path = ROOT / "assets" / "sightware-brand-256.png"
    png_path.parent.mkdir(exist_ok=True)
    img.save(png_path)

    ico_path = ROOT / "sightware.ico"
    img.save(ico_path, format="ICO",
             sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])
    print(f"wrote {png_path}")
    print(f"wrote {ico_path}")


if __name__ == "__main__":
    main()
