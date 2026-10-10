"""Яркость и разница соседних кадров в диапазоне: stats.py video.mp4 start_s end_s"""
import sys

import av
import numpy as np

video, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
prev = None
with av.open(video) as c:
    s = c.streams.video[0]
    c.seek(int(max(0, t0 - 1) / s.time_base), stream=s)
    for fr in c.decode(s):
        if fr.time < t0:
            continue
        if fr.time > t1:
            break
        a = fr.to_ndarray(format="gray").astype(np.float32)[::4, ::4]
        d = 0.0 if prev is None else float(np.abs(a - prev).mean())
        print(f"{fr.time:6.3f}s f{round(fr.time * 59.94):4d} bright={a.mean():6.1f} diff={d:5.1f}")
        prev = a
