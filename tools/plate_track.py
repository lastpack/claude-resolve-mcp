"""Трекинг номера (CSRT) от рамки на первом кадре: plate_track.py path t0 t1 x y w h out.json [sheet.jpg]
Координаты — пиксели исходника. Рамка сглаживается; в json — [{t, box}] на каждый кадр."""
import json
import sys

import av
import cv2
import numpy as np

path, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
box0 = tuple(int(v) for v in sys.argv[4:8])
out = sys.argv[8]
sheet = sys.argv[9] if len(sys.argv) > 9 else None
res, snaps = [], []
tr = None
with av.open(path) as c:
    s = c.streams.video[0]
    c.seek(int(max(0, t0 - 1) / s.time_base), stream=s)
    for f in c.decode(s):
        t = float(f.pts * s.time_base)
        if t < t0 - 0.008:
            continue
        if t > t1:
            break
        img = cv2.cvtColor(f.to_ndarray(format="rgb24"), cv2.COLOR_RGB2BGR)
        if tr is None:
            tr = cv2.TrackerCSRT_create()
            tr.init(img, box0)
            b = box0
        else:
            ok, b = tr.update(img)
            if not ok:
                b = res[-1]["box"]
        res.append({"t": round(t, 4), "box": [float(v) for v in b]})
        if sheet and len(res) % 12 == 1:
            snaps.append((t, img.copy(), b))
arr = np.array([r["box"] for r in res])
sm = np.array([arr[max(0, i - 3):i + 4].mean(axis=0) for i in range(len(arr))])
for r, b in zip(res, sm):
    r["box"] = [round(float(v), 1) for v in b]
json.dump(res, open(out, "w"), indent=0)
print("кадров", len(res))
if sheet:
    tiles = []
    for t, img, _ in snaps:
        b = next(r["box"] for r in res if abs(r["t"] - t) < 0.009)
        x, y, w, h = [int(v) for v in b]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 6)
        cv2.putText(img, f"{t:.2f}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 255, 255), 5)
        tiles.append(cv2.resize(img, (480, 270)))
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    cv2.imwrite(sheet, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
