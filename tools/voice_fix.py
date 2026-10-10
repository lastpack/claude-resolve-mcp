"""Голос: взять канал (по умолчанию левый), сделать моно по центру, громкость к цели с запасом по пику.
voice_fix.py src start_s dur_s out.wav [target_lufs=-16] [channel=0]"""
import subprocess
import sys

import imageio_ffmpeg
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

src, start, dur, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
target = float(sys.argv[5]) if len(sys.argv) > 5 else -16.0
ch = int(sys.argv[6]) if len(sys.argv) > 6 else 0
SR = 48000
raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-ss", str(start), "-t", str(dur), "-i", src,
                      "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
a = np.frombuffer(raw, np.float32).reshape(-1, 2)[:, ch].copy()
st = np.stack([a, a], 1)
lufs = pyln.Meter(SR).integrated_loudness(st)
gain = target - lufs
peak_db = 20 * np.log10(np.abs(a).max())
# мягкий лимитер для редких пиков: всё, что выше -1.5 dBFS после усиления, мягко поджимаем
g = 10 ** (gain / 20)
y = a * g
thr = 10 ** (-3.0 / 20)
over = np.abs(y) > thr
y[over] = np.sign(y[over]) * (thr + (1 - thr) * np.tanh((np.abs(y[over]) - thr) / (1 - thr)) * 0.85)
y = np.stack([y, y], 1)
sf.write(out, y, SR, subtype="PCM_24")
print(f"src {lufs:.1f} LUFS, peak {peak_db:.1f} dBFS -> gain {gain:+.1f} dB, out peak "
      f"{20 * np.log10(np.abs(y).max()):.1f} dBFS, out {pyln.Meter(SR).integrated_loudness(y):.1f} LUFS")
