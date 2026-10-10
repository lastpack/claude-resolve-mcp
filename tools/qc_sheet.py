"""Раскадровка видео для проверки глазами: qc_sheet.py video.mp4 start end step out.jpg [cols] [thumb_w]
Подпись — время в секундах (время таймлайна)."""
import sys

import av
from PIL import Image, ImageDraw

path, a, b, step, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 6
W = int(sys.argv[7]) if len(sys.argv) > 7 else 300
times = []
t = a
while t < b - 1e-6:
    times.append(round(t, 3))
    t += step
got = {}
with av.open(path) as c:
    s = c.streams.video[0]
    c.seek(int(max(0, a - 1) / s.time_base), stream=s)
    ti = 0
    for f in c.decode(s):
        ft = float(f.pts * s.time_base)
        while ti < len(times) and ft >= times[ti] - 0.5 / 59.94:
            got[times[ti]] = f.to_image().resize((W, round(W * f.height / f.width)))
            ti += 1
        if ti >= len(times):
            break
H = next(iter(got.values())).height
rows = (len(times) + cols - 1) // cols
sheet = Image.new("RGB", (cols * W, rows * (H + 14)), (12, 12, 12))
d = ImageDraw.Draw(sheet)
for i, tt in enumerate(times):
    x, y = (i % cols) * W, (i // cols) * (H + 14)
    if tt in got:
        sheet.paste(got[tt], (x, y + 14))
    d.text((x + 3, y + 1), f"{tt:.2f}", fill=(230, 230, 120))
sheet.save(out, quality=85)
print(out)
