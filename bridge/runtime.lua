-- Обработчик запросов моста. Перечитывается на каждый запрос: правки применяются без перезапуска.
-- Возвращает function(ctx) -> { ok, result | error, stdout }.
local TB = (debug and debug.traceback) or function(e) return tostring(e) end

return function(ctx)
  local logs = {}
  local env = setmetatable({}, { __index = _G })
  env.resolve, env.fusion, env.ffi, env.C = ctx.resolve, ctx.fusion, ctx.ffi, ctx.C
  env.read_file, env.write_file, env.to_json = ctx.read_file, ctx.write_file, ctx.to_json
  env.print = function(...)
    local t = {}
    for i = 1, select('#', ...) do t[#t + 1] = tostring(select(i, ...)) end
    logs[#logs + 1] = table.concat(t, '\t')
  end

  local hf, herr = loadfile(ctx.HELPERS)
  if hf then
    setfenv(hf, env)
    local ok, err = xpcall(hf, TB)
    if not ok then return { ok = false, error = 'helpers.lua: ' .. tostring(err) } end
  elseif not tostring(herr):find('cannot open') then
    return { ok = false, error = 'helpers.lua: ' .. tostring(herr) }
  end

  local fn, err = loadfile(ctx.REQ)
  ctx.C.remove(ctx.REQ)
  if not fn then return { ok = false, error = 'syntax: ' .. tostring(err) } end
  setfenv(fn, env)
  local ok, res = xpcall(fn, TB)
  if not ok then return { ok = false, error = tostring(res), stdout = table.concat(logs, '\n') } end
  return { ok = true, result = res, stdout = table.concat(logs, '\n') }
end
