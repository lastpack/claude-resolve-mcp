"""Маркеры (таймлайна и клипов) с заметками + дыры на V1/V2 текущего таймлайна -> work/plan/marks.json"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from resolve_mcp import bridge_client as b  # noqa: E402

r = b.run("""local tl = timeline()
local t0 = tl:GetStartFrame()
local out = {timeline = tl:GetName(), fps = fps(), markers = {}, clip_markers = {}, items = {}}
for f, m in pairs(tl:GetMarkers() or {}) do
  if type(m) == 'table' then
    out.markers[#out.markers + 1] = {frame = f, color = m.color, name = m.name, note = m.note, dur = m.duration}
  end
end
for tr = 1, tl:GetTrackCount('video') do
  for _, it in ipairs(items('video', tr)) do
    out.items[#out.items + 1] = {tr = tr, s = it:GetStart() - t0, e = it:GetEnd() - t0, name = it:GetName()}
    for f, m in pairs(it:GetMarkers() or {}) do
      if type(m) == 'table' then
        out.clip_markers[#out.clip_markers + 1] = {tr = tr, frame = it:GetStart() - t0 + f - it:GetLeftOffset(),
          color = m.color, name = m.name, note = m.note, dur = m.duration, clip = it:GetName()}
      end
    end
  end
end
return out""", timeout=60)
assert r.get("ok"), r
d = r["result"]
fps = d["fps"]
# дыры: кадры, где нет ни V1, ни V2
spans = sorted((i["s"], i["e"]) for i in d["items"] if i["tr"] in (1, 2))
gaps, cur = [], 0
for a, e in spans:
    if a > cur + 1:
        gaps.append([round(cur / fps, 3), round(a / fps, 3)])
    cur = max(cur, e)
end_f = round(110.393 * fps)
if cur < end_f - 2:
    gaps.append([round(cur / fps, 3), round(end_f / fps, 3)])
d["gaps"] = gaps
for m in d["markers"] + d["clip_markers"]:
    m["t"] = round(m["frame"] / fps, 3)
    m["t_end"] = round((m["frame"] + (m.get("dur") or 1)) / fps, 3)
(ROOT / "work/plan").mkdir(parents=True, exist_ok=True)
(ROOT / "work/plan/marks.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("таймлайн:", d["timeline"])
print("дыры:", gaps)
for m in sorted(d["markers"] + d["clip_markers"], key=lambda x: x["t"]):
    print(f"  {m['t']:7.2f}–{m['t_end']:7.2f}  [{m.get('color')}] {m.get('name') or ''} | {m.get('note') or ''}"
          + (f"  (клип V{m['tr']} {m['clip']})" if 'clip' in m else ""))
