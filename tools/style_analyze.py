"""Разбор монтажного стиля референса: склейки, длина планов, зумы, вспышки, тряска + раскадровка.
style_analyze.py video.mp4 out_prefix [--thumbs 24]"""
import json
import sys

import cv2
import numpy as np

video, prefix = sys.argv[1], sys.argv[2]
n_thumbs = int(sys.argv[sys.argv.index("--thumbs") + 1]) if "--thumbs" in sys.argv else 24

cap = cv2.VideoCapture(video)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
prev_g, prev_h = None, None
rows = []  # t, hist_diff, bright, divergence, shake
frames_small = []
i = 0
while True:
    ok, fr = cap.read()
    if not ok:
        break
    small = cv2.resize(fr, (160, int(160 * fr.shape[0] / fr.shape[1])))
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    h = cv2.calcHist([cv2.cvtColor(small, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(h, h)
    hd = 0.0 if prev_h is None else float(cv2.compareHist(prev_h, h, cv2.HISTCMP_BHATTACHARYYA))
    div = shake = 0.0
    if prev_g is not None and hd < 0.35:
        flow = cv2.calcOpticalFlowFarneback(prev_g, g, None, 0.5, 2, 9, 2, 5, 1.1, 0)
        H, W = g.shape
        ys, xs = np.mgrid[0:H, 0:W]
        rx, ry = xs - W / 2, ys - H / 2
        r = np.sqrt(rx ** 2 + ry ** 2) + 1e-6
        div = float(((flow[..., 0] * rx + flow[..., 1] * ry) / r).mean())  # >0 наезд, <0 отъезд
        shake = float(np.linalg.norm(flow.reshape(-1, 2).mean(0)))  # общий сдвиг кадра
    rows.append((i / fps, hd, float(g.mean()), div, shake))
    frames_small.append(fr if i % 2 == 0 else None)
    prev_g, prev_h = g, h
    i += 1
cap.release()

a = np.array(rows)
t, hd, br, dv, sh = a.T
cuts = [0] + [k for k in range(1, len(a)) if hd[k] > 0.35 and k - 1 > 0]
# склеить двойные срабатывания (переходы)
merged = []
for k in cuts:
    if not merged or k - merged[-1] > 3:
        merged.append(k)
cuts = merged
shots = np.diff(cuts + [len(a)]) / fps
dur = len(a) / fps

# зум-удары: резкие пики дивергенции; вспышки: скачок яркости без склейки; тряска: высокий shake
zoom_events = [round(t[k], 2) for k in range(2, len(a) - 2)
               if abs(dv[k]) > 0.6 and abs(dv[k]) == np.abs(dv[k - 2:k + 3]).max()]
flash_events = [round(t[k], 2) for k in range(1, len(a)) if br[k] - br[k - 1] > 25 and hd[k] < 0.35]
shake_frac = float((sh > 2.0).mean())

stats = {
    "file": video, "duration_s": round(dur, 1), "fps": round(fps, 2), "cuts": len(cuts) - 1,
    "cuts_per_min": round((len(cuts) - 1) / dur * 60, 1),
    "shot_s": {"median": round(float(np.median(shots)), 2), "mean": round(float(shots.mean()), 2),
               "p10": round(float(np.percentile(shots, 10)), 2), "p90": round(float(np.percentile(shots, 90)), 2)},
    "short_shots_lt_0.5s_pct": round(float((shots < 0.5).mean() * 100), 1),
    "zoom_events_per_min": round(len(zoom_events) / dur * 60, 1), "zoom_events": zoom_events[:30],
    "flash_events": flash_events[:20], "shaky_frames_pct": round(shake_frac * 100, 1),
}
print(json.dumps(stats, ensure_ascii=False))
json.dump(stats, open(prefix + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# раскадровка: середина каждого плана, первые n_thumbs планов
cap = cv2.VideoCapture(video)
thumbs = []
for s, e in list(zip(cuts, cuts[1:] + [len(a)]))[:n_thumbs]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, (s + e) // 2)
    ok, fr = cap.read()
    if ok:
        w = 200 if fr.shape[1] > fr.shape[0] else 112
        im = cv2.resize(fr, (w, int(w * fr.shape[0] / fr.shape[1])))
        cv2.putText(im, f"{t[s]:.1f}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        thumbs.append(im)
cap.release()
cols = 8 if thumbs[0].shape[1] > thumbs[0].shape[0] else 12
hh, ww = thumbs[0].shape[:2]
rows_n = (len(thumbs) + cols - 1) // cols
sheet = np.zeros((rows_n * hh, cols * ww, 3), np.uint8)
for k, im in enumerate(thumbs):
    sheet[(k // cols) * hh:(k // cols) * hh + im.shape[0], (k % cols) * ww:(k % cols) * ww + im.shape[1]] = im
cv2.imwrite(prefix + "_sheet.jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 75])
