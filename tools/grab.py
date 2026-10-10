"""Вытащить кадры из видео по секундам: grab.py video.mp4 out_prefix t1 t2 ..."""
import sys

import av

video, prefix, times = sys.argv[1], sys.argv[2], [float(t) for t in sys.argv[3:]]
with av.open(video) as c:
    s = c.streams.video[0]
    print("duration:", float(c.duration / 1e6), "fps:", float(s.average_rate), "frames:", s.frames)
    for i, t in enumerate(times):
        c.seek(int(max(0, t - 1) / s.time_base), stream=s)
        for fr in c.decode(s):
            if fr.time >= t:
                fr.to_image().save(f"{prefix}{i + 1}.png")
                break
