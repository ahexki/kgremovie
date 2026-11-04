r"""Draws the app icon (HUD theme: near-black navy, cyan corner brackets, play triangle).

Run:  py -3.12 app\make_icon.py
Writes app\assets\icon.png (256 px, used for the Tk window) and app\assets\icon.ico (multi-size, used by Windows).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent / "assets"
BG = (5, 8, 13, 255)          # controller.BG
PANEL = (10, 18, 28, 255)     # controller.PANEL
BORDER = (23, 58, 82, 255)    # controller.BORDER
ACCENT = (0, 229, 255, 255)   # controller.ACCENT
ACCENT_DIM = (11, 58, 71, 255)
SIZE = 1024                   # drawn large, then scaled down for smooth edges


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((32, 32, SIZE - 32, SIZE - 32), radius=190, fill=BG, outline=BORDER, width=14)
    d.rounded_rectangle((110, 110, SIZE - 110, SIZE - 110), radius=90, fill=PANEL)

    # Corner brackets
    arm, w, lo, hi = 190, 38, 150, SIZE - 150
    for x, sx in ((lo, 1), (hi, -1)):
        for y, sy in ((lo, 1), (hi, -1)):
            d.line((x, y, x + sx * arm, y), fill=ACCENT, width=w)
            d.line((x, y, x, y + sy * arm), fill=ACCENT, width=w)
            d.ellipse((x - w // 2, y - w // 2, x + w // 2, y + w // 2), fill=ACCENT)
            ex, ey = x + sx * arm, y + sy * arm
            d.ellipse((ex - w // 2, y - w // 2, ex + w // 2, y + w // 2), fill=ACCENT)
            d.ellipse((x - w // 2, ey - w // 2, x + w // 2, ey + w // 2), fill=ACCENT)

    # Glow behind the play triangle
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    tri = [(400, 330), (400, 694), (720, 512)]
    gd.polygon(tri, fill=ACCENT_DIM)
    glow = glow.filter(ImageFilter.GaussianBlur(45))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    d.polygon(tri, fill=ACCENT)
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    big = draw_icon()
    big.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    big.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Wrote", ASSETS / "icon.png", "and", ASSETS / "icon.ico")


if __name__ == "__main__":
    main()
