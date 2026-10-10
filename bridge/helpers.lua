-- Функции, доступные коду, который выполняется внутри Resolve через мост (перечитывается на каждый запрос).

function vals(t)
  local r = {}
  for k, v in pairs(t or {}) do
    if type(v) == 'userdata' then r[#r + 1] = v elseif type(k) == 'userdata' then r[#r + 1] = k end
  end
  return r
end

function project()
  local p = resolve:GetProjectManager():GetCurrentProject()
  assert(p, 'нет открытого проекта')
  return p
end

function timeline()
  local t = project():GetCurrentTimeline()
  assert(t, 'нет активного таймлайна')
  return t
end

function fps() return tonumber(timeline():GetSetting('timelineFrameRate')) end
function sec(s) return math.max(1, math.floor(s * fps() + 0.5)) end

function items(kind, track)
  local r = vals(timeline():GetItemListInTrack(kind or 'video', track))
  table.sort(r, function(a, b) return a:GetStart() < b:GetStart() end)
  return r
end

function item_info(it, tr)
  return { name = it:GetName(), start = it:GetStart(), ['end'] = it:GetEnd(), track = tr,
           comps = it:GetFusionCompCount() }
end

-- клип на видеотреке в кадре f (сверху вниз, если track не задан)
function item_at(f, track)
  local tl = timeline()
  local from, to = track or tl:GetTrackCount('video'), track or 1
  for tr = from, to, -1 do
    for _, it in ipairs(items('video', tr)) do
      -- только клипы с медиа (титры/генераторы/переходы пропускаем)
      if it:GetStart() <= f and f < it:GetEnd() and (track or it:GetMediaPoolItem()) then return it, tr end
    end
  end
  error('нет видеоклипа в кадре ' .. tostring(f))
end

-- ------------------------------------------------------------- Fusion
function clip_comp(it)
  local comp = it:GetFusionCompCount() > 0 and it:GetFusionCompByIndex(1) or nil
  comp = comp or it:AddFusionComp()
  assert(comp, 'не удалось создать Fusion-композицию')
  return comp
end

-- кадр таймлайна -> время в композиции клипа
function ctime(comp, it, f)
  return comp:GetAttrs().COMPN_RenderStart + (f - it:GetStart())
end

function last_before_out(comp)
  local mout = comp:FindTool('MediaOut1')
  assert(mout, 'нет MediaOut1')
  local o = mout:FindMainInput(1):GetConnectedOutput()
  return mout, (o and o:GetTool()) or comp:FindTool('MediaIn1')
end

function chain(comp, id, name)
  local mout, last = last_before_out(comp)
  local t = comp:AddTool(id, -32768, -32768)
  if name then t:SetAttrs({ TOOLS_Name = name }) end
  t:ConnectInput('Input', last)
  mout:ConnectInput('Input', t)
  return t
end

-- анимация входа: kv = {{t, v}, ...}; для точек path=true и v={x,y}
-- AddModifier сам ставит ключ в CurrentTime композиции (значение по умолчанию). Если CurrentTime раньше
-- нашего первого ключа, анимация «наплывает» с начала клипа (призраки титров, ранний блюр). Поэтому на
-- время AddModifier переводим CurrentTime на первый ключ — лишний ключ перезапишется нашим.
-- До первого ключа держится его значение: нейтральное «до эффекта» задавай первым ключом.
function keys(tool, input, kv, path)
  local comp = tool:Comp()
  local cur = comp.CurrentTime
  comp.CurrentTime = kv[1][1]
  tool:AddModifier(input, path and 'XYPath' or 'BezierSpline')
  comp.CurrentTime = cur
  for _, p in ipairs(kv) do
    local v = p[2]
    if path then v = { v[1], v[2] } end
    tool:SetInput(input, v, p[1])
  end
end

local function fx_begin(f, track)
  local it, tr = item_at(f, track)
  local comp = clip_comp(it)
  comp:Lock()
  return it, tr, comp, ctime(comp, it, f)
end

-- Композиции, изменённые через API, Resolve не рендерит, пока правка не пройдёт через систему undo
-- (как правка в UI). Пустое отменяемое действие «активирует» композицию.
-- The node is an Underlay (graph backdrop, no inputs/outputs). It used to be a Background, but when the comp was
-- open in the Fusion page, Fusion auto-connected the Background to the selected node through a Merge; the
-- Background got deleted, the Merge with a dangling Foreground stayed in the chain, and several of those hung
-- the render (reproduced: 4 effects on one clip -> render stuck at 43%).
function activate(comp)
  comp:StartUndo('activate')
  local d = comp:AddTool('Underlay', -32768, -32768)
  if d then d:Delete() end
  comp:EndUndo(true)
end

-- Remove dangling Merges (Foreground not connected) left by the old activation: the next node is reconnected
-- to the Background source. Returns the number removed.
function fix_orphan_merges(comp)
  local n = 0
  for _, t in pairs(comp:GetToolList(false, 'Merge') or {}) do
    if type(t) ~= 'number' then
      local fg = t:FindMainInput(2)
      local bgout = t:FindMainInput(1) and t:FindMainInput(1):GetConnectedOutput()
      if fg and not fg:GetConnectedOutput() and bgout then
        for _, inp in pairs(t:FindMainOutput(1):GetConnectedInputs() or {}) do
          if type(inp) ~= 'number' then inp:ConnectTo(bgout) end
        end
        t:Delete()
        n = n + 1
      end
    end
  end
  return n
end

function activate_all(from, to)
  local n = 0
  local tl = timeline()
  for tr = 1, tl:GetTrackCount('video') do
    for _, it in ipairs(items('video', tr)) do
      if it:GetEnd() > (from or -1) and it:GetStart() < (to or 1e12) and it:GetFusionCompCount() > 0 then
        local comp = it:GetFusionCompByIndex(1)
        fix_orphan_merges(comp)
        activate(comp); n = n + 1
      end
    end
  end
  return n
end

local function fx_end(comp, name, it, tr, f)
  comp:Unlock()
  activate(comp)
  return { fx = name, clip = it:GetName(), track = tr, frame = f }
end

-- ------------------------------------------------------------- эффекты
function fx_zoom_punch(f, amount, ret, track, hold)
  amount, ret = amount or 1.15, ret or 0.4
  local it, tr, comp, t0 = fx_begin(f, track)
  local z = chain(comp, 'Transform', 'ZoomPunch')
  local th = t0 + ((hold and hold > 0) and sec(hold) or 0)
  keys(z, 'Size', th > t0 and { { t0 - 1, 1.0 }, { t0, amount }, { th, amount }, { th + sec(ret), 1.0 } }
                           or { { t0 - 1, 1.0 }, { t0, amount }, { t0 + sec(ret), 1.0 } })
  return fx_end(comp, 'zoom_punch', it, tr, f)
end

function fx_slow_zoom(f, dur, amount, track)
  amount = amount or 1.08
  local it, tr, comp, t0 = fx_begin(f, track)
  local z = chain(comp, 'Transform', 'SlowZoom')
  local t1 = dur and (t0 + sec(dur)) or ctime(comp, it, it:GetEnd() - 1)
  keys(z, 'Size', { { t0, 1.0 }, { t1, amount } })
  return fx_end(comp, 'slow_zoom', it, tr, f)
end

function fx_shake(f, dur, k, track, seed)
  dur, k = dur or 0.5, k or 0.015
  math.randomseed(seed or f)
  local it, tr, comp, t0 = fx_begin(f, track)
  local n = sec(dur)
  local s = chain(comp, 'Transform', 'Shake')
  local pts = { { t0 - 1, { 0.5, 0.5 } } }
  for i = 0, n - 1, 2 do
    local a = k * (1 - i / n)
    pts[#pts + 1] = { t0 + i, { 0.5 + (math.random() * 2 - 1) * a, 0.5 + (math.random() * 2 - 1) * a } }
  end
  pts[#pts + 1] = { t0 + n, { 0.5, 0.5 } }
  keys(s, 'Center', pts, true)
  keys(s, 'Size', { { t0 - 1, 1.0 }, { t0, 1 + k * 3 }, { t0 + n, 1 + k * 3 }, { t0 + n + 1, 1.0 } })
  return fx_end(comp, 'shake', it, tr, f)
end

function fx_flash(f, dur, gain, track)
  dur, gain = dur or 0.25, gain or 2.2
  local it, tr, comp, t0 = fx_begin(f, track)
  local b = chain(comp, 'BrightnessContrast', 'Flash')
  keys(b, 'Gain', { { t0 - 1, 1.0 }, { t0, gain }, { t0 + sec(dur), 1.0 } })
  return fx_end(comp, 'flash', it, tr, f)
end

function fx_blur_in(f, dur, amount, track)
  dur, amount = dur or 0.4, amount or 25
  local it, tr, comp, t0 = fx_begin(f, track)
  local b = chain(comp, 'Blur', 'BlurIn')
  keys(b, 'XBlurSize', { { t0 - 1, 0 }, { t0, amount }, { t0 + sec(dur), 0 } })
  return fx_end(comp, 'blur_in', it, tr, f)
end

-- глитч: рывки по X, RGB-сдвиг красного канала, мерцание
function fx_glitch(f, dur, k, track, seed)
  dur, k = dur or 0.3, k or 1.0
  math.randomseed(seed or f)
  local it, tr, comp, t0 = fx_begin(f, track)
  local n = sec(dur)
  -- ChannelBoolean (RGB-сдвиг) ломал рендер композиции — оставлены рывки и мерцание
  local jit = chain(comp, 'Transform', 'GlitchJitter')
  local bc = chain(comp, 'BrightnessContrast', 'GlitchFlicker')
  local p2, g = { { t0 - 1, { 0.5, 0.5 } } }, { { t0 - 1, 1.0 } }
  for i = 0, n - 1 do
    local on = math.random() < 0.7
    local a = on and 0.03 * k or 0
    p2[#p2 + 1] = { t0 + i, { 0.5 + ((math.random() < 0.5) and (math.random() * 2 - 1) * a or 0), 0.5 } }
    g[#g + 1] = { t0 + i, on and (1 + (math.random() * 0.9 - 0.3) * k) or 1.0 }
  end
  p2[#p2 + 1] = { t0 + n, { 0.5, 0.5 } }
  g[#g + 1] = { t0 + n, 1.0 }
  keys(jit, 'Center', p2, true)
  keys(bc, 'Gain', g)
  return fx_end(comp, 'glitch', it, tr, f)
end

-- DeleteFusionCompByName на единственной композиции клипа ничего не удаляет, поэтому чистим узлы:
-- всё, кроме MediaIn1/MediaOut1, и соединяем их напрямую.
function clear_fx(f, track)
  local it, tr = item_at(f, track)
  local removed = 0
  for i = 1, it:GetFusionCompCount() do
    local comp = it:GetFusionCompByIndex(i)
    local names = {}
    for _, t in pairs(comp:GetToolList(false) or {}) do
      if type(t) ~= 'number' and t.Name ~= 'MediaIn1' and t.Name ~= 'MediaOut1' then names[#names + 1] = t.Name end
    end
    comp:Lock()
    for _, nm in ipairs(names) do
      local t = comp:FindTool(nm)  -- модификаторы могут уйти вместе с родителем
      if t then t:Delete(); removed = removed + 1 end
    end
    comp:FindTool('MediaOut1'):ConnectInput('Input', comp:FindTool('MediaIn1'))
    comp:Unlock()
    activate(comp)
  end
  return { clip = it:GetName(), track = tr, removed = removed }
end

-- ------------------------------------------------------------- превью
function export_frame(f, path)
  local tl = timeline()
  local page = resolve:GetCurrentPage()
  resolve:OpenPage('color')
  local r = math.floor(fps() + 0.5)
  local tc_start = tl:GetStartTimecode()
  tl:SetCurrentTimecode(frame_to_tc(f))
  local ok = project():ExportCurrentFrameAsStill(path)
  if page then resolve:OpenPage(page) end
  return ok
end

local function tc_abs(tc)
  local r = math.floor(fps() + 0.5)
  local h, m, s, fr = tc:match('(%d+):(%d+):(%d+)[:;](%d+)')
  assert(h, 'не таймкод: ' .. tostring(tc))
  return ((tonumber(h) * 60 + tonumber(m)) * 60 + tonumber(s)) * r + tonumber(fr)
end

function frame_to_tc(f)
  -- timecode от начала таймлайна с учётом его стартового таймкода
  local tl = timeline()
  local r = math.floor(fps() + 0.5)
  local abs = tc_abs(tl:GetStartTimecode()) + (f - tl:GetStartFrame())
  return string.format('%02d:%02d:%02d:%02d', math.floor(abs / (r * 3600)), math.floor(abs / (r * 60)) % 60,
    math.floor(abs / r) % 60, abs % r)
end

function tc_to_frame(tc)
  local tl = timeline()
  return tl:GetStartFrame() + tc_abs(tc) - tc_abs(tl:GetStartTimecode())
end

-- время для MCP: nil/'playhead' | секунды (12.5, '0:15', '1:02.5') | '01:00:15:12' | 'f360' (кадр от начала)
function to_frame(at)
  local tl = timeline()
  if at == nil or at == 'playhead' then return tc_to_frame(tl:GetCurrentTimecode()) end
  if type(at) == 'number' then return tl:GetStartFrame() + math.floor(at * fps() + 0.5) end
  at = tostring(at)
  local fr = at:match('^f(%d+)$')
  if fr then return tl:GetStartFrame() + tonumber(fr) end
  if at:match('^%d+:%d+:%d+[:;]%d+$') then return tc_to_frame(at) end
  local s = 0
  for part in at:gmatch('[^:]+') do s = s * 60 + assert(tonumber(part), 'не время: ' .. at) end
  return tl:GetStartFrame() + math.floor(s * fps() + 0.5)
end

-- ------------------------------------------------------------- виньетка и текст
function fx_vignette(f, strength, track)
  strength = strength or 0.6
  local it, tr, comp = fx_begin(f, track)
  local bc = chain(comp, 'BrightnessContrast', 'Vignette')
  bc:SetInput('Gain', 1 - strength)
  local m = comp:AddTool('EllipseMask', -32768, -32768)
  m:SetInput('Width', 0.85); m:SetInput('Height', 0.85); m:SetInput('SoftEdge', 0.25); m:SetInput('Invert', 1)
  bc:ConnectInput('EffectMask', m)
  return fx_end(comp, 'vignette', it, tr, f)
end

local function hex_rgb(c)
  local r, g, b = tostring(c or '#FFFFFF'):match('#?(%x%x)(%x%x)(%x%x)')
  return tonumber(r or 'FF', 16) / 255, tonumber(g or 'FF', 16) / 255, tonumber(b or 'FF', 16) / 255
end

-- p: text, duration, anim(pop|fade|slide_up|slide_left|blur|none), position{x,y}, size, color, font, style,
--    outline, shadow, tracking, anim_time. Текст живёт в Fusion-композиции клипа под ним.
-- Цепочка: TextPlus -> [Blur] -> Shadow -> Merge(Foreground) поверх видео.
function fx_text(f, p, track)
  local it, tr, comp, t0 = fx_begin(f, track)
  local t1 = t0 + sec(p.duration or 2.0)
  local a = sec(p.anim_time or 0.35)
  local ex = math.min(sec(0.18), math.floor((t1 - t0) / 4))   -- короткий уход в конце
  local anim = p.anim or 'pop'
  local x, y = (p.position or {})[1] or 0.5, (p.position or {})[2] or 0.2
  local size = p.size or 0.075
  local mout, last = last_before_out(comp)

  local txt = comp:AddTool('TextPlus', -32768, -32768)
  txt:SetInput('StyledText', p.text or '')
  txt:SetInput('Font', p.font or 'Arial'); txt:SetInput('Style', p.style or 'Regular')
  txt:SetInput('CharacterSpacing', p.tracking or 1.0)
  local r, g, b = hex_rgb(p.color)
  txt:SetInput('Red1', r); txt:SetInput('Green1', g); txt:SetInput('Blue1', b)
  if p.outline then  -- тонкая тёмная обводка, по желанию
    txt:SetInput('Enabled2', 1); txt:SetInput('Thickness2', 0.02)
    txt:SetInput('Red2', 0); txt:SetInput('Green2', 0); txt:SetInput('Blue2', 0)
  end

  local src = txt
  if anim == 'blur' then
    local bl = comp:AddTool('Blur', -32768, -32768)
    bl:ConnectInput('Input', src)
    keys(bl, 'XBlurSize', { { t0, 25 }, { t0 + a, 0 } })
    src = bl
  end
  if p.shadow then  -- мягкая тень, по желанию
    local sh = comp:AddTool('Shadow', -32768, -32768)
    sh:SetAttrs({ TOOLS_Name = 'TextShadow' })
    sh:ConnectInput('Input', src)
    sh:SetInput('ShadowOffset', { 0.503, 0.494 })
    sh:SetInput('Softness', 0.05)
    sh:SetInput('Red', 0); sh:SetInput('Green', 0); sh:SetInput('Blue', 0); sh:SetInput('Alpha', 0.75)
    src = sh
  end

  local mg = comp:AddTool('Merge', -32768, -32768)
  mg:SetAttrs({ TOOLS_Name = 'TextMerge' })
  mg:ConnectInput('Background', last); mg:ConnectInput('Foreground', src)
  mout:ConnectInput('Input', mg)

  -- видимость: быстрое проявление (у fade — во всё anim_time) и короткий уход в конце
  if anim == 'none' then
    keys(mg, 'Blend', { { t0 - 1, 0 }, { t0, 1 }, { t1, 1 }, { t1 + 1, 0 } })
  else
    local fin = (anim == 'fade') and a or math.max(1, math.floor(a * (anim == 'pop' and 0.4 or 0.6)))
    local out = (anim == 'fade') and a or ex
    keys(mg, 'Blend', { { t0, 0 }, { t0 + fin, 1 }, { t1 - out, 1 }, { t1, 0 } })
  end

  if anim == 'pop' then  -- пружина: 60% -> 108% -> 100%, на уходе чуть сжимается
    keys(txt, 'Size', { { t0, size * 0.6 }, { t0 + math.floor(a * 0.6), size * 1.08 }, { t0 + a, size },
                        { t1 - ex, size }, { t1, size * 0.92 } })
  else
    txt:SetInput('Size', size)
  end
  if anim == 'slide_up' then
    keys(txt, 'Center', { { t0, { x, y - 0.05 } }, { t0 + a, { x, y } } }, true)
  elseif anim == 'slide_left' then
    keys(txt, 'Center', { { t0, { x + 0.08, y } }, { t0 + a, { x, y } } }, true)
  else
    txt:SetInput('Center', { x, y })
  end
  return fx_end(comp, 'text', it, tr, f)
end

-- ------------------------------------------------------------- эффекты в стиле OsamaSon
-- строб: белые вспышки через кадр, frames — длительность в кадрах
function fx_strobe(f, frames, gain, track)
  frames, gain = frames or 8, gain or 3.0
  local it, tr, comp, t0 = fx_begin(f, track)
  local b = chain(comp, 'BrightnessContrast', 'Strobe')
  local kv = { { t0 - 1, 1.0 } }
  for i = 0, frames - 1 do kv[#kv + 1] = { t0 + i, (i % 4 < 2) and gain or 1.0 } end
  kv[#kv + 1] = { t0 + frames, 1.0 }
  keys(b, 'Gain', kv)
  return fx_end(comp, 'strobe', it, tr, f)
end

-- RGB-сдвиг без ChannelBoolean (он валил рендер): два Transform, каждый двигает только свой канал
function fx_rgb_split(f, px, dur, track)
  px, dur = px or 12, dur or 0.2
  local it, tr, comp, t0 = fx_begin(f, track)
  local w = tonumber(timeline():GetSetting('timelineResolutionWidth')) or 1440
  local d = px / w
  local n = sec(dur)
  for _, c in ipairs({ { 'Red', 1 }, { 'Blue', -1 } }) do
    local t = chain(comp, 'Transform', 'RGB' .. c[1])
    for _, ch in ipairs({ 'Red', 'Green', 'Blue', 'Alpha' }) do t:SetInput('Process' .. ch, ch == c[1] and 1 or 0) end
    keys(t, 'Center', { { t0 - 1, { 0.5, 0.5 } }, { t0, { 0.5 + d * c[2], 0.5 } }, { t0 + n, { 0.5, 0.5 } } }, true)
  end
  return fx_end(comp, 'rgb_split', it, tr, f)
end

-- тинт на весь клип: mono (ч/б контраст), red (красный монохром), night (зелёный «ночник»)
function fx_tint(f, mode, track)
  mode = mode or 'mono'
  local it, tr, comp = fx_begin(f, track)
  local b = chain(comp, 'BrightnessContrast', 'Tint_' .. mode)
  b:SetInput('Saturation', 0)
  b:SetInput('Contrast', mode == 'night' and 0.3 or 0.2)
  if mode ~= 'mono' then
    local g = chain(comp, 'ColorGain', 'TintGain_' .. mode)
    local rgb = mode == 'red' and { 1.25, 0.32, 0.28 } or { 0.35, 1.15, 0.2 }
    g:SetInput('GainRed', rgb[1]); g:SetInput('GainGreen', rgb[2]); g:SetInput('GainBlue', rgb[3])
  end
  return fx_end(comp, 'tint_' .. mode, it, tr, f)
end

-- пересвет (дневной «мир» референса)
function fx_overexpose(f, gain, track)
  local it, tr, comp = fx_begin(f, track)
  local b = chain(comp, 'BrightnessContrast', 'Overexpose')
  b:SetInput('Gain', gain or 1.35)
  b:SetInput('Lift', 0.04)
  return fx_end(comp, 'overexpose', it, tr, f)
end

-- ------------------------------------------------------------- точки входа для MCP-сервера
local FX = {
  zoom_punch = function(f, t, p) return fx_zoom_punch(f, p.amount, p.duration, t, p.hold) end,
  slow_zoom  = function(f, t, p) return fx_slow_zoom(f, p.duration, p.amount, t) end,
  shake      = function(f, t, p) return fx_shake(f, p.duration, p.intensity, t, p.seed) end,
  flash      = function(f, t, p) return fx_flash(f, p.duration, p.strength, t) end,
  blur_in    = function(f, t, p) return fx_blur_in(f, p.duration, p.amount, t) end,
  glitch     = function(f, t, p) return fx_glitch(f, p.duration, p.intensity, t, p.seed) end,
  vignette   = function(f, t, p) return fx_vignette(f, p.strength, t) end,
  strobe     = function(f, t, p) return fx_strobe(f, p.frames, p.gain, t) end,
  rgb_split  = function(f, t, p) return fx_rgb_split(f, p.px, p.dur, t) end,
  tint       = function(f, t, p) return fx_tint(f, p.mode, t) end,
  overexpose = function(f, t, p) return fx_overexpose(f, p.gain, t) end,
}

function mcp_fx(name, at, track, p)
  assert(FX[name], 'нет эффекта ' .. tostring(name))
  return FX[name](to_frame(at), track, p or {})
end

function mcp_status()
  local p = resolve:GetProjectManager():GetCurrentProject()
  local tl = p and p:GetCurrentTimeline()
  local r = { product = resolve:GetProductName(), version = resolve:GetVersionString(),
              page = resolve:GetCurrentPage(), project = p and p:GetName() }
  if tl then
    r.timeline, r.fps = tl:GetName(), fps()
    r.resolution = tl:GetSetting('timelineResolutionWidth') .. 'x' .. tl:GetSetting('timelineResolutionHeight')
    r.playhead, r.start_tc = tl:GetCurrentTimecode(), tl:GetStartTimecode()
    r.duration_s = math.floor((tl:GetEndFrame() - tl:GetStartFrame()) / fps() * 100 + 0.5) / 100
    r.video_tracks, r.audio_tracks = tl:GetTrackCount('video'), tl:GetTrackCount('audio')
  end
  return r
end

function mcp_clips(track)
  local r = {}
  local from, to = track or 1, track or timeline():GetTrackCount('video')
  for tr = from, to do
    for _, it in ipairs(items('video', tr)) do
      local i = item_info(it, tr)
      i.start_tc, i.dur_s = frame_to_tc(i.start), math.floor((i['end'] - i.start) / fps() * 100 + 0.5) / 100
      r[#r + 1] = i
    end
  end
  return r
end

function mcp_transform(props, at, track)
  local it, tr = item_at(to_frame(at), track)
  local ok = true
  for k, v in pairs(props) do ok = it:SetProperty(k, v) and ok end
  return { ok = ok, clip = it:GetName(), track = tr }
end

function mcp_playhead(at)
  timeline():SetCurrentTimecode(frame_to_tc(to_frame(at)))
  return timeline():GetCurrentTimecode()
end

function mcp_marker(at, color, name, note, dur)
  return timeline():AddMarker(to_frame(at) - timeline():GetStartFrame(), color, name, note, dur)
end

function mcp_import(paths, append)
  local mp = project():GetMediaPool()
  local got = vals(mp:ImportMedia(paths))
  local names = {}
  for _, i in ipairs(got) do names[#names + 1] = i:GetName() end
  if append and #got > 0 then mp:AppendToTimeline(got) end
  return names
end

function mcp_render(dir, name, preset, s, e)
  local p = project()
  if preset then assert(p:LoadRenderPreset(preset), 'нет пресета ' .. preset) end
  local st = { TargetDir = dir, CustomName = name }
  if s ~= nil and e ~= nil then st.MarkIn, st.MarkOut = to_frame(s), to_frame(e)
  else st.SelectAllFrames = true end  -- иначе остаётся диапазон от прошлого рендера
  activate_all(st.MarkIn, st.MarkOut)
  p:SetRenderSettings(st)
  local jid = p:AddRenderJob()
  return { job = jid, started = p:StartRendering({ jid }) }
end

function mcp_render_status()
  local r = {}
  for _, j in pairs(project():GetRenderJobList() or {}) do  -- в списке есть служебный __flags
    if type(j) == 'table' then
      for k, v in pairs(project():GetRenderJobStatus(j.JobId) or {}) do
        if k ~= '__flags' then j[k] = v end
      end
      j.__flags = nil
      r[#r + 1] = j
    end
  end
  return r
end
