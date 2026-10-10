"""Привязать прокси (tools/make_proxies.py) к клипам медиапула: MediaPoolItem:LinkProxyMedia. Оригиналы не меняются;
отвязать — UnlinkProxyMedia или в Media Pool: правый клик -> Proxy Media -> Unlink.
link_proxies.py <те же файлы/папки, что и для make_proxies.py>"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from resolve_mcp import bridge_client as b  # noqa: E402
from make_proxies import paths, proxy_of  # noqa: E402

pairs = {p: str(proxy_of(p)) for p in paths if proxy_of(p).exists()}
r = b.run(f"""
local want = {b.lua(pairs)}
local out = {{linked = {{}}, fail = {{}}}}
local function walk(f)
  for _, c in pairs(f:GetClipList() or {{}}) do
    if type(c) ~= 'number' then
      local px = want[c:GetClipProperty('File Path')]
      if px then
        if c:LinkProxyMedia(px) then out.linked[#out.linked + 1] = c:GetName()
        else out.fail[#out.fail + 1] = c:GetName() end
      end
    end
  end
  for _, s in pairs(f:GetSubFolderList() or {{}}) do if type(s) ~= 'number' then walk(s) end end
end
walk(project():GetMediaPool():GetRootFolder())
out.saved = resolve:GetProjectManager():SaveProject()
return out
""", timeout=300)
print(json.dumps(r, ensure_ascii=False, indent=1))
