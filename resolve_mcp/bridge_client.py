"""Клиент к Lua-мосту ResolveBridge, запущенному внутри DaVinci Resolve (файловый протокол)."""
import json
import os
import threading
import time
from pathlib import Path

QUEUE = Path(__file__).resolve().parent.parent / "queue"
REQ, RESP, ALIVE, STOP = (QUEUE / n for n in ("req.lua", "resp.json", "alive", "stop"))
_lock = threading.Lock()


class BridgeError(RuntimeError):
    pass


def lua(value) -> str:
    """Python-значение -> литерал Lua."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # JSON-строка — валидная строка Lua
    if isinstance(value, (list, tuple)):
        return "{" + ", ".join(lua(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ", ".join(f"[{lua(k)}] = {lua(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"не могу передать в Lua: {type(value).__name__}")


def is_running() -> bool:
    try:
        return ALIVE.read_text(encoding="utf-8").strip() == "running"
    except OSError:
        return False


def run(code: str, timeout: float = 600.0) -> dict:
    """Выполнить Lua-код внутри Resolve. Ответ — то, что код вернул через `return`."""
    if not is_running():
        start = (QUEUE.parent / "bridge" / "start.lua").as_posix()
        raise BridgeError("Bridge is not running. In DaVinci Resolve: Workspace > Console, Lua tab: "
                          f"dofile([[{start}]])  (run install.ps1 first if start.lua is missing)")
    QUEUE.mkdir(exist_ok=True)
    with _lock:
        RESP.unlink(missing_ok=True)
        tmp = QUEUE / "req.tmp"
        tmp.write_text(code, encoding="utf-8")
        os.replace(tmp, REQ)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if RESP.exists():
                try:
                    data = json.loads(RESP.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    time.sleep(0.05)
                    continue
                RESP.unlink(missing_ok=True)
                return data
            time.sleep(0.03)
        REQ.unlink(missing_ok=True)
    raise BridgeError("Мост не ответил вовремя (Resolve занят/завис или мост остановлен)")


def stop() -> None:
    """Попросить мост остановиться."""
    STOP.write_text(str(time.time_ns()), encoding="utf-8")


def call(fn: str, *args) -> object:
    """Вызвать функцию из helpers.lua и вернуть результат, либо бросить BridgeError."""
    r = run(f"return {fn}({', '.join(lua(a) for a in args)})")
    if not r.get("ok"):
        raise BridgeError(r.get("error", "unknown error"))
    return r.get("result")


if __name__ == "__main__":
    import sys
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else
                         "return {product = resolve:GetProductName(), version = resolve:GetVersionString()}"),
                     ensure_ascii=False, indent=2))
