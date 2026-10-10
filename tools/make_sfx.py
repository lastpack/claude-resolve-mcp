"""Синтез простой библиотеки звуков для саунд-дизайна (48 кГц, стерео, пик -6 dBFS): make_sfx.py out_dir"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)


def t(d):
    return np.arange(int(d * SR)) / SR


def env(n, a=0.002, r=None, curve=4.0):
    x = np.linspace(0, 1, n)
    e = np.exp(-curve * x) if r is None else np.clip(1 - x / r, 0, 1) ** curve
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def lowpass(x, cutoff):
    # однополюсный ФНЧ; cutoff может быть массивом (развёртка)
    c = np.broadcast_to(np.asarray(cutoff, float), x.shape)
    a = np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def sweep(f0, f1, d, shape=1.0):
    tt = t(d)
    f = f0 + (f1 - f0) * (tt / d) ** shape
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def stereo(x, width=0.0):
    if width <= 0:
        return np.stack([x, x], 1)
    d = int(width * SR)
    return np.stack([x, np.concatenate([np.zeros(d), x[:-d]])], 1)


def save(name, x):
    x = x / (np.abs(x).max() + 1e-9) * 10 ** (-6 / 20)
    sf.write(out / f"{name}.wav", x.astype(np.float32), SR)
    print(name, f"{len(x) / SR:.2f}s")


# удар: питч-даун синус + щелчок + шумовой хвост
d = 1.4
body = sweep(140, 42, d, 0.25) * env(int(d * SR), curve=3.5)
click = rng.standard_normal(int(0.01 * SR)) * env(int(0.01 * SR), curve=8)
tail = lowpass(rng.standard_normal(int(d * SR)), 1800) * env(int(d * SR), curve=6) * 0.5
x = body
x[: len(click)] += click * 0.8
save("impact", stereo(np.tanh(1.8 * (x + tail)), 0.004))

# саб-дроп
d = 1.8
save("subdrop", stereo(np.tanh(1.5 * sweep(90, 28, d, 0.6) * env(int(d * SR), a=0.01, curve=2.2))))

# райзер: шум с открывающимся фильтром + восходящий тон, обрыв в конце
d = 2.5
n = int(d * SR)
ramp = np.linspace(0, 1, n) ** 2
noise = lowpass(rng.standard_normal(n), 300 + 9000 * ramp) * ramp
tone = sweep(200, 1400, d, 2.0) * ramp * 0.25
save("riser", stereo(noise + tone, 0.006))

# реверс-свелл: развёрнутый «хвост реверберации»
d = 1.2
n = int(d * SR)
rev = lowpass(rng.standard_normal(n), 2500) * env(n, curve=5)
rev += sweep(330, 300, d) * env(n, curve=5) * 0.3
save("reverse_swell", stereo(rev[::-1], 0.008))

# глитч-статтер: рваные цифровые обрывки
d = 0.45
n = int(d * SR)
x = np.zeros(n)
pos = 0
while pos < n:
    L = int(rng.uniform(0.012, 0.045) * SR)
    seg = np.sign(np.sin(2 * np.pi * rng.uniform(80, 900) * np.arange(L) / SR)) * rng.uniform(0.3, 1)
    if rng.random() < 0.3:
        seg = rng.standard_normal(L) * 0.6
    seg = seg[: n - pos]
    x[pos:pos + len(seg)] = seg * (rng.random() < 0.8)
    pos += L
save("glitch", stereo(x * env(n, a=0.001, r=1.0, curve=0.5)))

# щелчок затвора (под фриз/стоп-кадр)
d = 0.25
n = int(d * SR)
x = np.zeros(n)
for off, g in ((0, 1.0), (0.06, 0.6)):
    i = int(off * SR)
    L = int(0.012 * SR)
    x[i:i + L] += lowpass(rng.standard_normal(L), 6000) * env(L, curve=10) * g
save("shutter", stereo(x))

# «вспышка»: короткий яркий шумовой всплеск с хвостом (под стробы/flash)
d = 0.6
n = int(d * SR)
x = (rng.standard_normal(n) - lowpass(rng.standard_normal(n), 1500)) * env(n, curve=9)
save("flash_hit", stereo(x, 0.003))
