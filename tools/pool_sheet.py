"""Раскадровка всех клипов Media Pool: по 1 кадру из середины каждого видео. pool_sheet.py pool.json out.jpg"""
import json
import sys

import cv2
import numpy as np

pool = [c for c in json.load(open(sys.argv[1], encoding="utf-8")) if "Video" in (c.get("type") or "")]
pool.sort(key=lambda c: c["name"])
W, H = 192, 108
tiles = []
for i, c in enumerate(pool):
    # cv2 не любит кириллицу в путях — читаем через буфер не получится для видео, поэтому пробуем как есть
    cap = cv2.VideoCapture(c["path"])
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n * 0.4))
    ok, fr = cap.read()
    cap.release()
    im = cv2.resize(fr, (W, H)) if ok else np.zeros((H, W, 3), np.uint8)
    cv2.rectangle(im, (0, 0), (W, 14), (0, 0, 0), -1)
    cv2.putText(im, f"{i} {c['name'][-8:-4]} {c['dur'][3:8]}", (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
    tiles.append(im)
    c["idx"] = i
cols = 10
rows = (len(tiles) + cols - 1) // cols
sheet = np.zeros((rows * H, cols * W, 3), np.uint8)
for i, im in enumerate(tiles):
    sheet[(i // cols) * H:(i // cols + 1) * H, (i % cols) * W:(i % cols + 1) * W] = im
ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 70])
open(sys.argv[2], "wb").write(buf.tobytes())
json.dump(pool, open(sys.argv[1].replace(".json", "_idx.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(tiles), "clips")
