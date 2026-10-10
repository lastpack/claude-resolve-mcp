"""Анализ трека: слова с таймингом (Whisper), биты и энергия (librosa) -> JSON."""
import json
import sys
from pathlib import Path

import librosa
import numpy as np

src = Path(sys.argv[1])
out = Path(sys.argv[2])

y, sr = librosa.load(str(src), sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
beat_t = librosa.frames_to_time(beats, sr=sr).tolist()
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
rms = librosa.feature.rms(y=y)[0]
rms_t = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
# энергия по полсекунды
energy = [float(rms[(rms_t >= t) & (rms_t < t + 0.5)].mean()) for t in np.arange(0, len(y) / sr, 0.5)]
# сильные акценты (для эффектов)
strong = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time", backtrack=False)
strength = onset_env[librosa.time_to_frames(strong, sr=sr)]
thr = np.percentile(strength, 90) if len(strength) else 0
accents = [round(float(t), 3) for t, s in zip(strong, strength) if s >= thr]

from faster_whisper import WhisperModel  # noqa: E402

words = []
y16 = librosa.resample(y, orig_sr=sr, target_sr=16000).astype(np.float32)  # без PyAV
for device, ctype in (("cuda", "float32"), ("cuda", "int8_float32"), ("cpu", "int8")):
    try:
        model = WhisperModel("medium", device=device, compute_type=ctype)
        segs, info = model.transcribe(y16, language="ru", word_timestamps=True, vad_filter=False,
                                      beam_size=5)
        for s in segs:
            for w in s.words or []:
                words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)})
        print("whisper device:", device)
        break
    except Exception as e:  # noqa: BLE001
        print("whisper", device, "failed:", e)
        words = []

out.write_text(json.dumps({
    "duration": round(len(y) / sr, 3), "tempo": float(np.atleast_1d(tempo)[0]),
    "beats": [round(t, 3) for t in beat_t], "accents": accents,
    "energy_half_sec": [round(e, 4) for e in energy], "words": words,
}, ensure_ascii=False, indent=1), encoding="utf-8")
print("words:", len(words), "beats:", len(beat_t), "tempo:", tempo)
