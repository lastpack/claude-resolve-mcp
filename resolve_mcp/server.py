"""MCP-сервер для управления DaVinci Resolve (в том числе бесплатной версии) через Lua-мост ResolveBridge.

Логика живёт в bridge/helpers.lua (функции mcp_* и fx_*), сервер только вызывает их.

Время (`at`) во всех инструментах:
  - не указано / "playhead"  -> текущая позиция плейхеда
  - "0:15", "1:02.5", 12.5   -> секунды от начала таймлайна
  - "01:00:15:12"            -> абсолютный таймкод
  - "f360"                   -> кадр от начала таймлайна
"""
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image

from resolve_mcp import bridge_client

mcp = FastMCP("davinci-resolve")

At = str | float | None
WORK = Path(__file__).resolve().parent.parent / "work"


def call(fn: str, *args: Any) -> Any:
    """Вызвать Lua-функцию из helpers.lua внутри Resolve."""
    return bridge_client.call(fn, *args)


def _clean(**kw: Any) -> dict:
    return {k: v for k, v in kw.items() if v is not None}


@mcp.tool()
def resolve_status() -> dict:
    """Версия Resolve, открытый проект, таймлайн, fps, разрешение, позиция плейхеда, треки."""
    return call("mcp_status")


@mcp.tool()
def list_clips(track: int | None = None) -> list:
    """Список клипов на видеотреках (или на одном треке `track`), с таймкодами и длительностью."""
    return call("mcp_clips", track) or []


@mcp.tool()
def apply_effect(
    effect: Literal["zoom_punch", "slow_zoom", "shake", "flash", "blur_in", "glitch", "vignette",
                    "strobe", "rgb_split", "tint", "overexpose"],
    at: At = None,
    track: int | None = None,
    params: dict | None = None,
) -> dict:
    """Наложить моушен-эффект на клип в момент `at` (через Fusion-композицию клипа).

    Эффекты и их params:
      zoom_punch: amount=1.15, duration=0.4 (возврат, сек), hold=0.0
      slow_zoom:  amount=1.08, duration=до конца клипа
      shake:      intensity=0.015, duration=0.5, seed
      flash:      strength=2.2, duration=0.25
      blur_in:    amount=25, duration=0.4
      glitch:     intensity=1.0, duration=0.3, seed
      vignette:   strength=0.6 (на весь клип)
      strobe:     frames=8, gain=3.0 (белые вспышки через 2 кадра)
      rgb_split:  px=12, dur=0.2 (сдвиг красного/синего каналов, затухает)
      tint:       mode=mono|red|night (на весь клип)
      overexpose: gain=1.35 (на весь клип)
    Эффекты складываются в цепочку. Откат — clear_effects.
    """
    return call("mcp_fx", effect, at, track, params or {})


@mcp.tool()
def add_text(
    text: str,
    at: At = None,
    duration: float = 2.0,
    anim: Literal["pop", "fade", "slide_up", "slide_left", "blur", "none"] = "pop",
    x: float = 0.5,
    y: float = 0.2,
    size: float = 0.075,
    color: str = "#FFFFFF",
    font: str = "Arial",
    style: str = "Regular",
    upper: bool = False,
    shadow: bool = False,
    outline: bool = False,
    tracking: float = 1.0,
    anim_time: float = 0.35,
    track: int | None = None,
) -> dict:
    """Анимированный текст/титр поверх клипа. x,y — центр (0..1, y=0 низ). size ~0.05–0.15.
    Оформление задаёт пользователь: font/style — любой установленный в системе шрифт (для кириллицы проверь,
    что шрифт её поддерживает), upper — капс, shadow — мягкая тень, outline — тонкая обводка,
    tracking — межбуквенный интервал (1.0 = обычный). По умолчанию нейтрально: Arial Regular, белый.
    Текст живёт внутри Fusion-композиции клипа, поэтому обрезается по концу клипа."""
    p = _clean(text=text.upper() if upper else text, duration=duration, anim=anim, position=[x, y],
               size=size, color=color, font=font, style=style, shadow=shadow, outline=outline,
               tracking=tracking, anim_time=anim_time)
    return call("(function(f, p, t) return fx_text(to_frame(f), p, t) end)", at, p, track)


@mcp.tool()
def clear_effects(at: At = None, track: int | None = None) -> dict:
    """Удалить все Fusion-эффекты/титры с клипа в момент `at`."""
    return call("(function(f, t) return clear_fx(to_frame(f), t) end)", at, track)


@mcp.tool()
def set_clip_transform(properties: dict, at: At = None, track: int | None = None) -> dict:
    """Статичные свойства клипа из инспектора: ZoomX, ZoomY, Pan, Tilt, RotationAngle, FlipX,
    CropLeft/Right/Top/Bottom, Opacity, CompositeMode, AudioVolume и т.д. (см. TimelineItemProperties)."""
    return call("mcp_transform", properties, at, track)


@mcp.tool()
def set_playhead(at: At) -> str:
    """Переместить плейхед."""
    return call("mcp_playhead", at)


@mcp.tool()
def add_marker(at: At = None, name: str = "", note: str = "",
               color: str = "Blue", duration_frames: int = 1) -> bool:
    """Маркер на таймлайне (цвета: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose,
    Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream)."""
    return call("mcp_marker", at, color, name, note, duration_frames)


@mcp.tool()
def preview_frame(at: At = None) -> Image:
    """Снимок кадра таймлайна (с эффектами) — чтобы посмотреть результат.
    Ненадёжен для Fusion-эффектов: для проверки лучше рендер + tools/grab.py."""
    WORK.mkdir(exist_ok=True)
    path = WORK / "preview.png"
    path.unlink(missing_ok=True)
    call("(function(f, p) return export_frame(to_frame(f), p) end)", at, str(path))
    if not path.exists():
        raise bridge_client.BridgeError("Resolve не сохранил кадр")
    return Image(path=path)


@mcp.tool()
def import_media(paths: list[str], append_to_timeline: bool = False) -> list:
    """Импортировать файлы в Media Pool, опционально добавить в конец текущего таймлайна."""
    return call("mcp_import", paths, append_to_timeline) or []


@mcp.tool()
def render(output_dir: str, file_name: str, preset: str | None = None,
           start: At = None, end: At = None) -> dict:
    """Поставить рендер текущего таймлайна и запустить (Fusion-правки перед этим активируются).
    preset — имя пресета рендера (например 'YouTube - 1080p'). start/end — опциональный диапазон."""
    return call("mcp_render", output_dir, file_name, preset, start, end)


@mcp.tool()
def render_status() -> list:
    """Статус задач рендера."""
    return call("mcp_render_status") or []


@mcp.tool()
def run_resolve_lua(code: str) -> dict:
    """Выполнить произвольный Lua внутри Resolve. Доступны resolve, fusion, bmd и все функции
    bridge/helpers.lua (project(), timeline(), to_frame(), item_at(), clip_comp(), chain(), keys(),
    activate(), vals(), ...). Ответ — то, что код вернул через `return`. Для всего, чего нет в пресетах."""
    return bridge_client.run(code)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
