"""Draws the Hanpaper icon: an English page behind a Korean page marked 한 -> hanpaper.png/.ico (and .icns on macOS)."""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "hanpaper", "static", "fonts", "NanumGothic-Bold.ttf")
S = 1024
BLUE = (59, 91, 219, 255)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=BLUE)
# back page (English): lighter, tilted look by offset
d.rounded_rectangle([190, 190, 640, 760], radius=48, fill=(150, 168, 236, 255))
for i, y in enumerate((300, 370, 440, 510, 580)):
    d.rounded_rectangle([240, y, 560 - (90 if i == 4 else 0), y + 26], radius=13, fill=(205, 214, 248, 255))
# front page (Korean)
d.rounded_rectangle([380, 300, 834, 870], radius=52, fill=(255, 255, 255, 255))
font = ImageFont.truetype(FONT, 300)
t = "한"
w = d.textbbox((0, 0), t, font=font)
d.text((607 - (w[2] - w[0]) / 2 - w[0], 470 - (w[3] - w[1]) / 2 - w[1]), t, font=font, fill=BLUE)
for i, y in enumerate((690, 760)):
    d.rounded_rectangle([450, y, 764 - (110 if i == 1 else 0), y + 28], radius=14, fill=(170, 184, 240, 255))
img.save(os.path.join(HERE, "hanpaper.png"))
img.save(os.path.join(HERE, "hanpaper.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
if sys.platform == "darwin":
    iconset = os.path.join(HERE, "hanpaper.iconset")
    os.makedirs(iconset, exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        img.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
        img.resize((s * 2, s * 2), Image.LANCZOS).save(os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(HERE, "hanpaper.icns")], check=True)
print("icon ok")
