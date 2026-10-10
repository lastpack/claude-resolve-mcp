"""Поиск номерного знака (EU: белый прямоугольник ~4.7:1 с синей полосой слева) по кадрам исходника.
plates.py path t0 t1 out.json [sheet.jpg] -> [{t, box:[x,y,w,h]}] в координатах исходника (сглажено, с интерполяцией)."""
import json
import sys

import av
import cv2
import numpy as np

path, t0, t1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
sheet = sys.argv[5] if len(sys.argv) > 5 else None


def detect(img, prev=None):
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    white = cv2.inRange(hsv, (0, 0, 150), (180, 70, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8))
    cnts, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, bs = None, 0
    H, W = img.shape[:2]
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w < 40 or h < 10 or w > W * 0.5:
            continue
        ar = w / h
        if not 2.5 < ar < 6.5:
            continue
        fill = cv2.contourArea(c) / (w * h)
        if fill < 0.55:
            continue
        roi = img[y:y + h, x:x + w]
        g = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        dark = (g < 90).mean()  # буквы на номере
        if not 0.08 < dark < 0.6:
            continue
        sc = fill + dark + min(ar, 5) / 5
        if prev is not None:  # рядом с прошлым положением — выгоднее
            px, py, pw, ph = prev
            dist = np.hypot(x + w / 2 - px - pw / 2, y + h / 2 - py - ph / 2) / W
            sc -= dist * 6
        if sc > bs:
            best, bs = (x, y, w, h), sc
    return best


res, prev, frames = [], None, {}
with av.open(path) as c:
    s = c.streams.video[0]
    c.seek(int(max(0, t0 - 1) / s.time_base), stream=s)
    for f in c.decode(s):
        t = float(f.pts * s.time_base)
        if t < t0 - 0.01:
            continue
        if t > t1:
            break
        img = f.to_ndarray(format="rgb24")
        b = detect(img, prev)
        if b:
            prev = b
        res.append({"t": round(t, 4), "box": list(b) if b else None})
        if sheet and len(frames) < 12 and int(t * 4) not in frames:
            frames[int(t * 4)] = (t, img, b)
# заполнить пропуски интерполяцией и сгладить медианой по 5 кадрам
idx = [i for i, r in enumerate(res) if r["box"]]
if not idx:
    sys.exit("номер не найден")
arr = np.array([r["box"] if r["box"] else [np.nan] * 4 for r in res], float)
for k in range(4):
    v = arr[:, k]
    ok = ~np.isnan(v)
    arr[:, k] = np.interp(np.arange(len(v)), np.where(ok)[0], v[ok])
sm = np.array([np.median(arr[max(0, i - 2):i + 3], axis=0) for i in range(len(arr))])
for r, b in zip(res, sm):
    r["box"] = [round(float(x), 1) for x in b]
json.dump(res, open(out, "w"), indent=0)
print("кадров", len(res), "найдено", len(idx))
if sheet:
    from PIL import Image, ImageDraw
    tiles = []
    for _, (t, img, b) in sorted(frames.items()):
        im = Image.fromarray(img)
        bb = next(r["box"] for r in res if abs(r["t"] - t) < 0.01)
        ImageDraw.Draw(im).rectangle([bb[0], bb[1], bb[0] + bb[2], bb[1] + bb[3]], outline=(255, 0, 0), width=6)
        tiles.append(im.resize((480, 270)))
    shp = Image.new("RGB", (480 * 4, 270 * ((len(tiles) + 3) // 4)))
    for i, im in enumerate(tiles):
        shp.paste(im, ((i % 4) * 480, (i // 4) * 270))
    shp.save(sheet, quality=85)
