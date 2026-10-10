"""Громкость готового видео: общий LUFS, пик и LUFS по участкам. loud.py video.mp4 a-b c-d ..."""
import subprocess
import sys

import imageio_ffmpeg
import numpy as np
import pyloudnorm as pyln

SR = 48000
a = np.frombuffer(subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", sys.argv[1], "-ac", "2",
                                  "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
a = a.reshape(-1, 2)
m = pyln.Meter(SR)
print(f"всего: {m.integrated_loudness(a):.1f} LUFS, пик {20 * np.log10(np.abs(a).max()):.1f} dBFS")
for seg in sys.argv[2:]:
    s, e = map(float, seg.split("-"))
    print(f"{seg:>10}: {m.integrated_loudness(a[int(s * SR):int(e * SR)]):.1f} LUFS")
