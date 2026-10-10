"""Выполнить Lua-файл внутри Resolve через мост: uv run python tools/rl.py file.lua"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resolve_mcp import bridge_client as b  # noqa: E402

r = b.run(Path(sys.argv[1]).read_text(encoding="utf-8"))
if r.get("ok"):
    print(json.dumps(r.get("result"), ensure_ascii=False, indent=1))
    if r.get("stdout"):
        print("stdout:", r["stdout"])
else:
    print("ERROR:", r.get("error"))
    sys.exit(1)
