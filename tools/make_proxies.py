"""Прокси для плавного плейбека: исходники -> work/proxy/<имя>.mov (ProRes Proxy 960x540, та же частота,
звук PCM, метаданные/таймкод исходника). Кодирование по 2 файла параллельно. Потом tools/link_proxies.py.
Рендер (Deliver) берёт оригиналы — прокси только для монтажа.
make_proxies.py <файл или папка> [...]"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work/proxy"
OUT.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".m4v"}
paths = []
for arg in sys.argv[1:]:
    p = Path(arg)
    paths += sorted(str(f) for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT) if p.is_dir() else [str(p)]
paths = [p for p in paths if Path(p).exists()]


def proxy_of(p):
    return OUT / (Path(p).stem + "_" + Path(p).suffix[1:].lower() + ".mov")


def enc(p):
    out = proxy_of(p)
    if out.exists() and out.stat().st_size > 0:
        return f"есть  {out.name}"
    tmp = out.with_suffix(".part.mov")
    cmd = [FF, "-v", "error", "-y", "-i", p, "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "0",
           "-vf", "scale=960:540:flags=bilinear", "-c:v", "prores_ks", "-profile:v", "0", "-pix_fmt", "yuv422p10le",
           "-c:a", "pcm_s16le", "-threads", "6", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return f"ОШИБКА {Path(p).name}: {r.stderr[-300:]}"
    tmp.replace(out)
    return f"готов {out.name} {out.stat().st_size // 2**20} МБ"


if __name__ == "__main__":
    if not paths:
        sys.exit(__doc__)
    print(len(paths), "исходников", flush=True)
    with ThreadPoolExecutor(2) as ex:
        for msg in ex.map(enc, paths):
            print(msg, flush=True)
