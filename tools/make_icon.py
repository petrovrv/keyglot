"""Render assets/keyglot.ico (app icon: "Aя" on a blue-to-teal tile)."""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "assets")


def tile(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        k = y / size
        gd.line((0, y, size, y), fill=(int(37 + (13 - 37) * k), int(99 + (148 - 99) * k), int(235 + (136 - 235) * k), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, size - 9, size - 9), radius=size // 5, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("segoeuib.ttf", int(size * 0.46))
    text = "Aя"
    box = d.textbbox((0, 0), text, font=f)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), text, font=f,
           fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    im = tile()
    im.save(os.path.join(OUT, "keyglot.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    im.save(os.path.join(OUT, "keyglot.png"))
    print("ok")
