"""SRT -> дорожка субтитров текущего таймлайна (старые субтитры снимаются). subs_place.py file.srt [папка_медиапула]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from resolve_mcp import bridge_client as b  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
srt = str(Path(sys.argv[1]).resolve())
folder = sys.argv[2] if len(sys.argv) > 2 else ""
r = b.run(f"""
local tl = timeline()
local t0 = tl:GetStartFrame()
local mp = project():GetMediaPool()
local root = mp:GetRootFolder()
local f
for _, x in pairs(root:GetSubFolderList() or {{}}) do
  if type(x) ~= 'number' and x:GetName() == {b.lua(folder)} then f = x end
end
mp:SetCurrentFolder(f or root)
-- снять прежние субтитры и прежний импорт этого файла (повторный импорт подхватывает правки SRT)
local nsub = tl:GetTrackCount('subtitle')
local old = {{}}
for tr = 1, nsub do for _, it in ipairs(vals(tl:GetItemListInTrack('subtitle', tr))) do old[#old + 1] = it end end
if #old > 0 then tl:DeleteClips(old) end
for _, it in pairs((f or root):GetClipList() or {{}}) do
  if type(it) ~= 'number' and it:GetClipProperty('File Path') == {b.lua(srt)} then mp:DeleteClips({{it}}) end
end
local imp = vals(mp:ImportMedia({{{b.lua(srt)}}}))
assert(#imp == 1, 'SRT не импортирован')
local it = imp[1]
if tl:GetTrackCount('subtitle') == 0 then tl:AddTrack('subtitle') end
local res = vals(mp:AppendToTimeline({{{{mediaPoolItem = it, recordFrame = t0, trackIndex = 1}}}}))
local out = {{type = it:GetClipProperty('Type'), placed = #res, subtitle_tracks = tl:GetTrackCount('subtitle'),
  removed = #old}}
if tl:GetTrackCount('subtitle') > 0 then
  local s = vals(tl:GetItemListInTrack('subtitle', 1))
  table.sort(s, function(a, c) return a:GetStart() < c:GetStart() end)
  out.count = #s
  out.first = s[1] and {{s[1]:GetStart() - t0, s[1]:GetEnd() - t0, s[1]:GetName()}} or nil
  out.last = s[#s] and {{s[#s]:GetStart() - t0, s[#s]:GetEnd() - t0, s[#s]:GetName()}} or nil
end
return out
""", timeout=120)
print(json.dumps(r, ensure_ascii=False, indent=1))
