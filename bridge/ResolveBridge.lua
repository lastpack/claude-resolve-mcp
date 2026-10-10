--[==[
ResolveBridge (Lua) — запускается ВНУТРИ DaVinci Resolve через загрузчик bridge/start.lua (его создаёт install.ps1):
  Workspace > Console (Lua): dofile([[<repo>/bridge/start.lua]])
Загрузчик задаёт глобальную RESOLVE_MCP_ROOT — корень репозитория.
(Запуск из меню Workspace > Scripts не работает: там другое окружение, мост не стартует.)

В Resolve 21 Lua работает в песочнице: нет io/os. Поэтому:
  - запрос читаем через loadfile (это Lua-код),
  - ответ пишем через LuaJIT ffi (fopen/fwrite/rename/remove из CRT).

Протокол (папка queue\):
  клиент атомарно кладёт req.lua  -> мост выполняет, удаляет req.lua,
  пишет resp.json (через resp.tmp + rename). Клиент читает и удаляет resp.json.
  alive = "running" пока мост работает. Остановка: клиент меняет содержимое файла stop.
]==]

local REPO = assert(RESOLVE_MCP_ROOT, 'RESOLVE_MCP_ROOT не задан: запускай через загрузчик из install.ps1')
REPO = REPO:gsub('[\\/]+$', '')
local QUEUE = REPO .. '/queue'
local HELPERS = REPO .. '/bridge/helpers.lua'
local REQ, RESP, RESP_TMP = QUEUE .. '/req.lua', QUEUE .. '/resp.json', QUEUE .. '/resp.tmp'
local ALIVE, STOP = QUEUE .. '/alive', QUEUE .. '/stop'

resolve = resolve or Resolve()
fusion = fusion or (resolve and resolve:Fusion())

-- ------------------------------------------------------------- файлы через ffi
local ffi = ffi or require('ffi')
pcall(ffi.cdef, [[
  typedef struct _iobuf FILE;
  FILE *fopen(const char *path, const char *mode);
  size_t fwrite(const void *ptr, size_t size, size_t n, FILE *f);
  size_t fread(void *ptr, size_t size, size_t n, FILE *f);
  int fclose(FILE *f);
  int remove(const char *path);
  int rename(const char *from, const char *to);
]])
local ok_c, C = pcall(function() local _ = ffi.C.fopen; return ffi.C end)
if not ok_c then C = ffi.load('msvcrt') end

local function write_file(path, s)
  local f = C.fopen(path, 'wb')
  if f == nil then error('не могу открыть на запись: ' .. path) end
  C.fwrite(s, 1, #s, f)
  C.fclose(f)
end

local function read_file(path)
  local f = C.fopen(path, 'rb')
  if f == nil then return nil end
  local chunks, buf = {}, ffi.new('char[65536]')
  while true do
    local n = tonumber(C.fread(buf, 1, 65536, f))
    if n <= 0 then break end
    chunks[#chunks + 1] = ffi.string(buf, n)
  end
  C.fclose(f)
  return table.concat(chunks)
end

local function replace_file(src, dst)
  C.remove(dst)
  return C.rename(src, dst) == 0
end

-- ------------------------------------------------------------- JSON
local function esc(s)
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
  s = s:gsub('[%z\1-\31]', function(c) return string.format('\\u%04x', c:byte()) end)
  return s
end

local function is_array(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= 'number' then return false end
    n = n + 1
  end
  for i = 1, n do if t[i] == nil then return false end end
  return true, n
end

local function to_json_(v, depth)
  depth = depth or 0
  if depth > 20 then return '"<too deep>"' end
  local tv = type(v)
  if v == nil then return 'null'
  elseif tv == 'boolean' then return tostring(v)
  elseif tv == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then return 'null' end
    if v == math.floor(v) and math.abs(v) < 1e15 then return string.format('%d', v) end
    return string.format('%.6g', v)
  elseif tv == 'string' then return '"' .. esc(v) .. '"'
  elseif tv == 'table' then
    local arr, n = is_array(v)
    local parts = {}
    if arr and n > 0 then
      for i = 1, n do parts[#parts + 1] = to_json_(v[i], depth + 1) end
      return '[' .. table.concat(parts, ',') .. ']'
    end
    for k, val in pairs(v) do
      parts[#parts + 1] = '"' .. esc(tostring(k)) .. '":' .. to_json_(val, depth + 1)
    end
    if #parts == 0 then return arr and '[]' or '{}' end
    return '{' .. table.concat(parts, ',') .. '}'
  else
    return '"' .. esc(tostring(v)) .. '"'
  end
end

-- ------------------------------------------------------------- выполнение
local TB = (debug and debug.traceback) or function(e) return tostring(e) end
local function run_request()
  local logs = {}
  local env = setmetatable({}, { __index = _G })
  env.resolve, env.fusion, env.ffi = resolve, fusion, ffi
  env.read_file, env.write_file = read_file, write_file
  env.print = function(...)
    local t = {}
    for i = 1, select('#', ...) do t[#t + 1] = tostring(select(i, ...)) end
    logs[#logs + 1] = table.concat(t, '\t')
  end
  -- helpers.lua перечитывается каждый раз — правки без перезапуска Resolve
  local hf, herr = loadfile(HELPERS)
  if hf then
    setfenv(hf, env)
    local ok, err = xpcall(hf, TB)
    if not ok then return { ok = false, error = 'helpers.lua: ' .. tostring(err) } end
  elseif not tostring(herr):find('cannot open') then
    return { ok = false, error = 'helpers.lua: ' .. tostring(herr) }
  end
  local fn, err = loadfile(REQ)
  C.remove(REQ)
  if not fn then return { ok = false, error = 'syntax: ' .. tostring(err) } end
  setfenv(fn, env)
  local ok, res = xpcall(fn, TB)
  if not ok then return { ok = false, error = tostring(res), stdout = table.concat(logs, '\n') } end
  return { ok = true, result = res, stdout = table.concat(logs, '\n') }
end

-- ------------------------------------------------------------- цикл
if bmd and bmd.createdir then bmd.createdir(QUEUE) end
local stop_initial = read_file(STOP)
write_file(ALIVE, 'running')
print('[ResolveBridge] Lua-мост запущен: ' .. QUEUE .. ', resolve=' .. tostring(resolve ~= nil))

local RUNTIME = REPO .. '/bridge/runtime.lua'
local ctx = { resolve = resolve, fusion = fusion, ffi = ffi, C = C, read_file = read_file,
              write_file = write_file, to_json = to_json_, REQ = REQ, HELPERS = HELPERS }

-- runtime.lua (перечитывается на каждый запрос) возвращает function(ctx) -> таблица-ответ.
-- Если его нет или он сломан — используем встроенный run_request.
local function handle()
  local rf = loadfile(RUNTIME)
  if rf then
    local okr, handler = pcall(rf)
    if okr and type(handler) == 'function' then return handler(ctx) end
  end
  return run_request()
end

-- Resolve при закрытии ждёт окончания скриптов консоли: без этой проверки бесконечный цикл моста не давал ему
-- выйти (процесс висел без окна). При закрытии Resolve сначала закрывает проект -> мост выходит сам.
local tick, miss = 0, 0
local function resolve_alive()
  local ok, proj = pcall(function() return resolve:GetProjectManager():GetCurrentProject() end)
  return ok and proj ~= nil
end

while true do
  if read_file(STOP) ~= stop_initial then break end
  tick = tick + 1
  if tick % 20 == 0 then  -- ~раз в секунду
    if resolve_alive() then miss = 0 else miss = miss + 1 end
    if miss >= 3 then print('[ResolveBridge] проект закрыт / Resolve выходит — мост завершается'); break end
  end
  if fileexists(REQ) then
    local ok, resp = pcall(handle)
    if not ok then resp = { ok = false, error = 'bridge: ' .. tostring(resp) } end
    local okj, js = pcall(to_json_, resp)
    if not okj then js = to_json_({ ok = false, error = 'json: ' .. tostring(js) }) end
    write_file(RESP_TMP, js)
    replace_file(RESP_TMP, RESP)
  end
  wait(0.05)
end
write_file(ALIVE, 'stopped')
print('[ResolveBridge] остановлен')
