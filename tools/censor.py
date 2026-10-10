"""Пикселизация номера по треку: censor.py src.mp4 t0 t1 track.json out.mp4
Пишет копию куска исходника [t0, t1] (полное разрешение, почти без потерь) с мозаикой в рамке трека (+25% запаса)."""
import json
import subprocess
import sys

import av
import cv2
import imageio_ffmpeg
import numpy as np

path, t0, t1, tj, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5]
trk = json.load(open(tj))
ts = np.array([r["t"] for r in trk])
boxes = np.array([r["box"] for r in trk])
enc = None
with av.open(path) as c:
    s = c.streams.video[0]
    rate = s.average_rate
    c.seek(int(max(0, t0 - 1) / s.time_base), stream=s)
    for f in c.decode(s):
        t = float(f.pts * s.time_base)
        if t < t0 - 0.008:
            continue
        if t > t1:
            break
        img = f.to_ndarray(format="rgb24")
        H, W = img.shape[:2]
        if enc is None:
            enc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt",
                                    "rgb24", "-s", f"{W}x{H}", "-r", str(rate), "-i", "-", "-c:v", "libx264", "-crf", "10",
                                    "-preset", "medium", "-pix_fmt", "yuv420p", "-bf", "0", "-g", "30", out],
                                   stdin=subprocess.PIPE)
        if ts[0] - 0.05 <= t <= ts[-1] + 0.05:
            b = np.array([np.interp(t, ts, boxes[:, k]) for k in range(4)])
            x, y, w, h = b
            x, y, w, h = x - w * 0.125, y - h * 0.125, w * 1.25, h * 1.25
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1, y1 = min(W, int(x + w)), min(H, int(y + h))
            if x1 - x0 > 4 and y1 - y0 > 4:
                roi = img[y0:y1, x0:x1]
                bs = max(6, int((x1 - x0) / 7))  # ~7 блоков по ширине номера — не читается
                small = cv2.resize(roi, (max(1, (x1 - x0) // bs), max(1, (y1 - y0) // bs)), interpolation=cv2.INTER_AREA)
                img[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        enc.stdin.write(img.tobytes())
enc.stdin.close()
enc.wait()
print(out)
