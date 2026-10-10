"""Поиск эффекта, который вешает рендер: 6 клипов с разными сочетаниями fx, каждый рендерится отдельно
с таймаутом. Нужен клип Clip_02.mp4 в Media Pool текущего проекта (любое видео, переименуй под себя).`n--ui: эффекты добавляются, пока клип открыт на странице Fusion."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from resolve_mcp import bridge_client as b  # noqa: E402

F = 29.97
L = 60  # кадров на клип
CASES = [
    ("control_punch_flash", ["fx_zoom_punch({f}, 1.2, 0.4, 1)", "fx_flash({f}, 0.3, 2.2, 1)"]),
    ("glitch_only", ["fx_glitch({f}, 0.4, 1.2, 1)"]),
    ("rgb_only", ["fx_rgb_split({f}, 18, 0.4, 1)"]),
    ("glitch_then_rgb", ["fx_glitch({f}, 0.4, 1.2, 1)", "fx_rgb_split({f}, 18, 0.4, 1)"]),
    ("rgb_then_glitch", ["fx_rgb_split({f}, 18, 0.4, 1)", "fx_glitch({f}, 0.4, 1.2, 1)"]),
    ("punch_flash_glitch_rgb", ["fx_zoom_punch({f}, 1.2, 0.4, 1)", "fx_flash({f}, 0.3, 2.2, 1)",
                                "fx_glitch({f}, 0.4, 1.2, 1)", "fx_rgb_split({f}, 18, 0.4, 1)"]),
]


def lua(code, timeout=60):
    r = b.run(code, timeout=timeout)
    if not r.get("ok"):
        raise SystemExit(f"Lua error: {r.get('error')}")
    return r.get("result")


UI = "--ui" in sys.argv  # эффекты добавлять, пока клип открыт на странице Fusion (как при записи промо)
only = [a for a in sys.argv[1:] if not a.startswith("--")]  # можно указать имена кейсов
lua(f"""
local p, mp = project(), project():GetMediaPool()
local c
for _, x in ipairs(vals(mp:GetRootFolder():GetClipList())) do if x:GetName() == 'Clip_02.mp4' then c = x end end
assert(c, 'Clip_02.mp4 not in pool')
local tl = mp:CreateEmptyTimeline('bugtest ' .. tostring(p:GetTimelineCount() + 1))
p:SetCurrentTimeline(tl)
local infos = {{}}
for i = 0, {len(CASES) - 1} do
  infos[#infos + 1] = {{ mediaPoolItem = c, startFrame = 10, endFrame = 10 + {L}, trackIndex = 1,
    recordFrame = tl:GetStartFrame() + i * {L}, mediaType = 1 }}
end
mp:AppendToTimeline(infos)
return tl:GetName()""")

results = []
for i, (name, fxs) in enumerate(CASES):
    if only and name not in only:
        continue
    f = i * L + 15
    if UI:
        lua(f"timeline():SetCurrentTimecode(frame_to_tc({f})); resolve:OpenPage('fusion'); return true")
        time.sleep(1.8)
    calls = "\n".join(x.format(f=f) for x in fxs)
    tools = lua(f"""{calls}
local it = item_at({f}, 1)
local comp = it:GetFusionCompByIndex(1)
local out = {{}}
for _, t in pairs(comp:GetToolList(false) or {{}}) do
  if type(t) ~= 'number' then out[#out + 1] = t:GetAttrs().TOOLS_RegID .. ':' .. t.Name end
end
table.sort(out)
return out""")
    lua(f"""local p = project()
activate_all({i * L}, {(i + 1) * L})
resolve:OpenPage('deliver')
p:SetCurrentRenderFormatAndCodec('mp4', 'H264')
p:SetRenderSettings({{ SelectAllFrames = false, MarkIn = {i * L}, MarkOut = {(i + 1) * L - 1},
  TargetDir = {b.lua(str(ROOT / 'work' / 'bugtest'))}, CustomName = {b.lua(name)} }})
local job = p:AddRenderJob()
p:StartRendering({{ job }})
return job""")
    t0 = time.time()
    status = "?"
    while time.time() - t0 < 25:
        st = lua("""local p = project()
local last
for _, j in pairs(p:GetRenderJobList() or {}) do if type(j) == 'table' and j.JobId then last = j.JobId end end
local s = p:GetRenderJobStatus(last)
return { busy = p:IsRenderingInProgress(), st = s.JobStatus, pct = s.CompletionPercentage }""")
        if not st["busy"]:
            status = f"{st['st']} {st['pct']}%"
            break
        status = f"HANG? {st['st']} {st['pct']}%"
        time.sleep(0.5)
    sec = round(time.time() - t0, 1)
    nodes = [t for t in tools if not t.endswith((":MediaIn1", ":MediaOut1"))]
    results.append({"case": name, "render": status, "seconds": sec, "nodes": nodes})
    print(f"{name:24s} {status:22s} {sec:5.1f}s  nodes={len(nodes)}  merges={sum('Merge' in t for t in nodes)}", flush=True)
    if status.startswith("HANG"):
        print("render stuck — stopping tests", flush=True)
        break

out = ROOT / "work/bugtest/results.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
