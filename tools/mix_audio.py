"""Громкость: измерить голос (LUFS) -> нужный гейн в дБ; музыку свести с плавным даккингом под голосом.
mix_audio.py music.mp3 voice.mp4 voice_in_s voice_tl_start voice_tl_end duck_start duck_end total_s out.wav"""
import json
import subprocess
import sys

import imageio_ffmpeg
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

music, voice = sys.argv[1], sys.argv[2]
v_in, v_tl0, v_tl1, d0, d1, total = map(float, sys.argv[3:9])
out = sys.argv[9]
SR = 48000
ff = imageio_ffmpeg.get_ffmpeg_exe()

VOICE_LUFS = -15.0      # голос — громко и чётко (YouTube ~ -14 общий)
MUSIC_OPEN_LUFS = -15.0  # музыка без голоса — на уровне голоса
DUCK_DB = 13.0           # музыка под голосом тише голоса на столько
RAMP = 0.35              # плавность даккинга, с


def pcm(path, start, dur):
    cmd = [ff, "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path, "-ac", "2", "-ar", str(SR),
           "-f", "f32le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)
    return a.reshape(-1, 2)


meter = pyln.Meter(SR)
v = pcm(voice, v_in, v_tl1 - v_tl0)
v_lufs = meter.integrated_loudness(v)
voice_gain = VOICE_LUFS - v_lufs

m = pcm(music, 0, total)
# громкость музыки по открытым кускам (без голоса)
open_part = np.concatenate([m[: int(d0 * SR)], m[int(d1 * SR):]])
m_lufs = meter.integrated_loudness(open_part) if len(open_part) > SR * 0.5 else meter.integrated_loudness(m)
base = MUSIC_OPEN_LUFS - m_lufs
duck = (VOICE_LUFS - DUCK_DB) - MUSIC_OPEN_LUFS  # отрицательно

t = np.arange(len(m)) / SR
env_db = np.full_like(t, base)
down = np.clip((t - (d0 - RAMP)) / RAMP, 0, 1)
up = np.clip((d1 - t) / RAMP, 0, 1)
env_db += duck * np.minimum(down, up)
mixed = m * (10 ** (env_db / 20))[:, None]
peak = np.abs(mixed).max()
if peak > 0.98:
    mixed *= 0.98 / peak
sf.write(out, mixed, SR, subtype="PCM_24")

print(json.dumps({"voice_lufs": round(v_lufs, 1), "voice_gain_db": round(voice_gain, 1),
                  "music_lufs_open": round(m_lufs, 1), "music_base_db": round(base, 1),
                  "duck_db": round(duck, 1), "peak": round(float(peak), 3)}))
