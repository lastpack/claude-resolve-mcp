"""Склеить кадры в одну уменьшенную картинку: sheet.py out.jpg a.png b.png ... [--w 480]"""
import sys

from PIL import Image, ImageDraw

args = sys.argv[1:]
w = 480
if "--w" in args:
    i = args.index("--w")
    w = int(args[i + 1])
    del args[i:i + 2]
out, files = args[0], args[1:]
ims = [Image.open(f).convert("RGB") for f in files]
ims = [im.resize((w, round(im.height * w / im.width))) for im in ims]
cols = min(3, len(ims))
rows = (len(ims) + cols - 1) // cols
h = ims[0].height
sheet = Image.new("RGB", (cols * w, rows * h), "black")
for i, im in enumerate(ims):
    x, y = (i % cols) * w, (i // cols) * h
    sheet.paste(im, (x, y))
    ImageDraw.Draw(sheet).text((x + 6, y + 4), str(i + 1), fill="yellow")
sheet.save(out, quality=80)
