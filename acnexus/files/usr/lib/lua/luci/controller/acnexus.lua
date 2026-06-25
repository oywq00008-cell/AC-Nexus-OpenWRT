module("luci.controller.acnexus", package.seeall)

local cjson = require "luci.jsonc"
local CFG_PATH = "/root/.ac_controller/config.json"

-- 读取 config.json
local function read_cfg()
    local f = io.open(CFG_PATH, "r")
    if not f then return nil end
    local raw = f:read("*all")
    f:close()
    local ok, cfg = pcall(cjson.parse, raw)
    if ok then return cfg end
    return nil
end

-- 写入 config.json（原子写入）
local function write_cfg(cfg)
    -- 修复：确保 devices 内的 provider 不会被误写为数组
    local devs = cfg.devices or {}
    for provider, provider_devs in pairs(devs) do
        if type(provider_devs) ~= "table" or (type(provider_devs) == "table" and #provider_devs > 0 and provider_devs[1] ~= nil and next(provider_devs, 1) ~= nil) then
            -- 数组（#provider_devs > 0 且有整数键）→ 纠正为空对象
            cfg.devices[provider] = {}
        end
    end
    local tmp = CFG_PATH .. ".tmp"
    local f = io.open(tmp, "w")
    if not f then return false end
    local s = cjson.stringify(cfg, true)
    -- 修复 Lua cjson 将空 table {} 序列化为 [] 的问题
    -- 目标：将 devices 内空的 provider 和 schedule_templates 从 [] 恢复为 {}
    for provider in pairs(devs) do
        s = s:gsub('("' .. provider .. '"%s*:%s*)%[%]', '%1{}')
    end
    s = s:gsub('("schedule_templates"%s*:%s*)%[%]', '%1{}')
    f:write(s)
    f:close()
    return os.rename(tmp, CFG_PATH)
end

-- 跨品牌查找设备
local function find_device(cfg, mac)
    local devs = cfg.devices or {}
    for provider, provider_devs in pairs(devs) do
        if type(provider_devs) == "table" and provider_devs[mac] then
            return provider, provider_devs[mac]
        end
    end
    return nil, nil
end

-- 纯 Lua base64 解码（不走 shell，MIPS 每次省 3 次 fork）
local b64_idx = {}
do
    local t = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    for i = 1, #t do b64_idx[t:sub(i,i)] = i - 1 end
end

local function b64decode(s)
    s = s:gsub('[^A-Za-z0-9+/=]', '')
    local out, j = {}, 1
    for i = 1, #s, 4 do
        local a = b64_idx[s:sub(i, i)] or 0
        local b = b64_idx[s:sub(i+1, i+1)] or 0
        local c = b64_idx[s:sub(i+2, i+2)] or 0
        local d = b64_idx[s:sub(i+3, i+3)] or 0
        out[j] = string.char(a * 4 + math.floor(b / 16)); j = j + 1
        if s:sub(i+2, i+2) ~= '=' then
            out[j] = string.char((b % 16) * 16 + math.floor(c / 4)); j = j + 1
        end
        if s:sub(i+3, i+3) ~= '=' then
            out[j] = string.char((c % 4) * 64 + d); j = j + 1
        end
    end
    return table.concat(out)
end

-- 写 UCI 并提交（安全转义单引号）
local function uci_set(key, value)
    local safe = tostring(value):gsub("'", "'\\''")
    os.execute("uci set acnexus.settings." .. key .. "='" .. safe .. "' 2>/dev/null")
end
local function uci_commit()
    os.execute("uci commit acnexus 2>/dev/null")
    os.execute("rm -f /tmp/luci-indexcache* 2>/dev/null")
end

function index()
    entry({"admin", "services", "acnexus"},
        alias("admin", "services", "acnexus", "dashboard"),
        _("AC-Nexus"), 60).dependent = true

    entry({"admin", "services", "acnexus", "dashboard"},
        template("acnexus/dashboard"), _("控制面板"), 10)

    entry({"admin", "services", "acnexus", "settings"},
        cbi("acnexus"), _("设置"), 20)

    entry({"admin", "services", "acnexus", "api"},
        call("api")).dependent = true

    entry({"admin", "services", "acnexus", "log_download"},
        call("log_download")).dependent = true

    entry({"admin", "services", "acnexus", "download_guide"},
        call("download_guide")).dependent = true
end

function api()
    local cmd = luci.http.formvalue("cmd") or ""
    if string.match(cmd, "['\";$`|&<>]") then
        luci.http.status(400, "Bad Request")
        luci.http.prepare_content("application/json")
        luci.http.write(cjson.stringify({error = "非法命令"}))
        return
    end

    -- ═══════════ Lua 直接处理 ═══════════

    if cmd == "status_lite" then return status_lite() end
    if cmd == "log_dates" then return log_dates() end
    if string.match(cmd, "^switch ") then return switch_dev(string.sub(cmd, 8)) end
    if cmd == "set_location_quick" then return set_location_quick() end
    if string.match(cmd, "^save_name ") then return save_name(string.sub(cmd, 11)) end
    if string.match(cmd, "^delete_device ") then return delete_device(string.sub(cmd, 15)) end
    if string.match(cmd, "^set_location ") then return set_location(cmd) end
    if string.match(cmd, "^location_save ") then return set_location(cmd) end
    if string.match(cmd, "^save_schedule ") then return save_schedule(cmd) end
    if string.match(cmd, "^save_rules ") then return save_rules(cmd) end
    if string.match(cmd, "^save_device ") then return save_device(cmd) end
    if string.match(cmd, "^send ") then return send_cmd(cmd) end
    if cmd == "cmd_result" then return cmd_result() end

    -- ═══════════ Python 处理（必须在 Python 做的）═══════════
    local script = "/usr/lib/acnexus/acnexus_api.py"
    local p = io.popen("/usr/bin/python3 " .. script .. " '" .. cmd .. "' 2>/dev/null", "r")
    if p then
        local result = p:read("*all")
        p:close()
        luci.http.prepare_content("application/json")
        luci.http.write(result)
    else
        luci.http.write('{"error":"exec failed"}')
    end
end

-- ─── status_lite ───────────────────────────────────────────────
-- 纯只读：读 config.json + 天气/台风缓存，拼成 JSON 返回。
-- 不写文件、不重启 daemon、不同步 UCI——写入统一由 CBI on_commit 负责。
function status_lite()
    local cfg = read_cfg()
    -- 插件停用检测：UCI 为权威来源，config.json 仅作降级补充
    local p_en = io.popen("uci -q get acnexus.@acnexus[0].enabled 2>/dev/null || uci -q get acnexus.settings.enabled 2>/dev/null")
    local uci_enabled = p_en and p_en:read("*a"):gsub("%s+", "") or ""
    if p_en then p_en:close() end
    if uci_enabled == "1" then
        -- UCI 明确启用 → 无条件放行（不信任可能过期的 config.json）
    elseif uci_enabled == "0" then
        -- UCI 明确禁用
        luci.http.prepare_content("application/json")
        luci.http.write(cjson.stringify({disabled = true, devices = {}, weather = {}, location = cfg.location or {}}))
        return
    else
        -- UCI 缺失 enabled 行（Flag 已删除），回退到 config.json + daemon 检测
        if cfg and cfg.enabled == false then
            luci.http.prepare_content("application/json")
            luci.http.write(cjson.stringify({disabled = true, devices = {}, weather = {}, location = cfg.location or {}}))
            return
        end
        local p = io.popen("ps | grep [a]cnexus_service | wc -l 2>/dev/null")
        local raw = p and p:read("*a") or "0"
        if p then p:close() end
        local count = tonumber((raw:match("%d+") or "0")) or 0
        if count == 0 then
            luci.http.prepare_content("application/json")
            luci.http.write(cjson.stringify({disabled = true, devices = {}, weather = {}, location = cfg.location or {}}))
            return
        end
    end

    local result = { devices = {}, weather = { temp = "--", humidity = "--", text = "--" },
                     storm_dist = 99999, storm_name = "", online = false }

    if cfg then
        -- 设备列表 + 当前设备
        local devs = cfg.devices or {}
        for provider, provider_devs in pairs(devs) do
            if type(provider_devs) == "table" then
                for did, dev in pairs(provider_devs) do
                    if type(dev) == "table" then
                        table.insert(result.devices, {
                            mac = did, name = dev.name or dev.model or did, provider = provider,
                        })
                    end
                end
            end
        end
        local mac = cfg.current_device_mac or ""
        local brand = cfg.current_brand_type or "broadlink"
        local cd = (devs[brand] or {})[mac] or {}
        result.device_name = cd.name or cd.model or mac
        result.current_device_mac = mac
        result.device_info = { brand = cd.brand or "gree", brand_display = cd.brand_display or "", host = cd.host or "", port = cd.port or 80, mac = mac }
        result.schedule = {
            enabled = cd.schedule_enabled, active_template = cd.active_template or "",
            auto_adjust = cd.auto_adjust, template_name = cd.active_template or "--",
            templates = cfg.schedule_templates or {},
            rules = cd.temp_rules or {},
        }
        result.online = (cd.host ~= nil and cd.host ~= "")
        result.location = cfg.location or { lat = 39.9, lon = 116.4, name = "未设置" }
    end

    -- 天气缓存
    local wf = io.open("/tmp/acnexus_weather.json", "r")
    if wf then
        local wraw = wf:read("*all"); wf:close()
        local wok, wd = pcall(cjson.parse, wraw)
        if wok and wd and wd.data then
            result.weather = {
                temp = tostring(wd.data.temp or "--"),
                humidity = tostring(wd.data.humidity or wd.data.rh or "--"),
                text = wd.data.text or "--",
            }
        end
    end

    -- 台风：从完整缓存计算最近风暴（可靠简单，一个文件无竞态）
    local tf = io.open("/tmp/acnexus_typhoon.json", "r")
    if tf then
        local traw = tf:read("*all"); tf:close()
        local tok, td = pcall(cjson.parse, traw)
        if tok and td and td.data then
            local min_dist, close_name = 99999, ""
            local loc = result.location or {}
            local lat, lon = tonumber(loc.lat), tonumber(loc.lon)
            if lat and lon then
                for _, t in ipairs(td.data) do
                    if t.detail and t.detail.lat and t.detail.lon then
                        local dlat = tonumber(t.detail.lat) - lat
                        local dlon = tonumber(t.detail.lon) - lon
                        local dist = math.sqrt(dlat*dlat + dlon*dlon) * 111
                        if dist < min_dist then
                            min_dist = dist; close_name = t.cn or t.eng or ""
                        end
                    end
                end
            end
            result.storm_dist = math.floor(min_dist)
            result.storm_name = close_name
        end
    end

    luci.http.prepare_content("application/json")
    luci.http.write(cjson.stringify(result))
end

-- ─── switch ────────────────────────────────────────────────────
function switch_dev(mac)
    local cfg = read_cfg()
    if not cfg or not cfg.devices then
        luci.http.write(cjson.stringify({ok = false, error = "配置读取失败"})); return
    end
    local provider, dev = find_device(cfg, mac)
    if not dev then
        luci.http.write(cjson.stringify({ok = false, error = "设备不存在"})); return
    end
    cfg.current_device_mac = mac
    cfg.current_brand_type = provider
    write_cfg(cfg)
    luci.http.write(cjson.stringify({
        ok = true,
        device_name = dev.name or dev.model or mac,
        device_info = { brand = dev.brand or "gree", brand_display = dev.brand_display or "", host = dev.host or "", port = dev.port or 80, mac = mac },
        schedule = { enabled = (dev.schedule_enabled ~= nil and dev.schedule_enabled) or false, active_template = dev.active_template or "", auto_adjust = (dev.auto_adjust ~= nil and dev.auto_adjust) or false, rules = dev.temp_rules or {} },
        online = (dev.host ~= nil and dev.host ~= ""),
    }))
end

-- ─── set_location ──────────────────────────────────────────────
function set_location(cmd)
    -- 支持 set_location <b64> 和 location_save <b64> 两种格式
    local b64
    if string.match(cmd, "^set_location ") then
        b64 = string.sub(cmd, 14)
    else
        b64 = string.sub(cmd, 15)
    end
    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end

    local raw = b64decode(b64)
    if not raw or raw == "" then luci.http.write(cjson.stringify({ok = false, error = "解析失败"})); return end
    local ok, data = pcall(cjson.parse, raw)
    if not ok then luci.http.write(cjson.stringify({ok = false, error = "JSON 格式错误"})); return end

    cfg.location = { lat = tonumber(data.lat) or 39.9, lon = tonumber(data.lon) or 116.4, name = data.name or "" }
    write_cfg(cfg)
    uci_set("location_lat", data.lat)
    uci_set("location_lon", data.lon)
    uci_set("location_name", data.name)
    uci_commit()
    -- 清除旧天气缓存 + 重启后台服务立即拉新位置天气
    os.execute("rm -f /tmp/acnexus_weather.json 2>/dev/null")
    os.execute("/etc/init.d/acnexus restart 2>/dev/null &")
    luci.http.write(cjson.stringify({ok = true}))
end

-- ─── save_name ─────────────────────────────────────────────────
function save_name(cmd)
    -- cmd 格式: save_name <b64 JSON {"mac":"...","name":"..."}>
    local b64 = cmd
    local raw = b64decode(b64)
    if not raw or raw == "" then luci.http.write(cjson.stringify({ok = false})); return end
    local ok, data = pcall(cjson.parse, raw)
    if not ok then luci.http.write(cjson.stringify({ok = false})); return end

    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end
    local _, dev = find_device(cfg, data.mac or "")
    if not dev then luci.http.write(cjson.stringify({ok = false, error = "设备不存在"})); return end
    dev.name = data.name or dev.model or data.mac
    write_cfg(cfg)
    luci.http.write(cjson.stringify({ok = true}))
end

-- ─── delete_device ─────────────────────────────────────────────
function delete_device(cmd)
    local mac = cmd
    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end
    local provider, _ = find_device(cfg, mac)
    if not provider then luci.http.write(cjson.stringify({ok = false, error = "设备不存在"})); return end
    cfg.devices[provider][mac] = nil
    if cfg.current_device_mac == mac then cfg.current_device_mac = "" end
    write_cfg(cfg)
    luci.http.write(cjson.stringify({ok = true}))
end

-- ─── save_device（设备设置弹窗保存）──────────────────────────
function save_device(cmd)
    -- cmd 格式: save_device <b64 JSON {"mac":"...","name":"...","brand":"...",...}>
    local b64 = string.sub(cmd, 13)
    local raw = b64decode(b64)
    if not raw or raw == "" then luci.http.write(cjson.stringify({ok = false})); return end
    local ok, data = pcall(cjson.parse, raw)
    if not ok then luci.http.write(cjson.stringify({ok = false})); return end

    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end
    local mac = data.mac or cfg.current_device_mac or ""
    local provider, dev = find_device(cfg, mac)
    if not dev then
        -- 新设备（扫描发现后保存）
        cfg.devices = cfg.devices or {}
        cfg.devices.broadlink = cfg.devices.broadlink or {}
        dev = { mac = mac, model = "博联设备", host = data.host or "", port = data.port or 80,
                brand = "gree", schedule_enabled = false, auto_adjust = false }
        cfg.devices.broadlink[mac] = dev
        if not cfg.current_device_mac or cfg.current_device_mac == "" then
            cfg.current_device_mac = mac
            cfg.current_brand_type = "broadlink"
        end
    end
    -- 只更新传入的字段，不覆盖已有配置
    if data.name and data.name ~= "" then dev.name = data.name end
    if not dev.name then dev.name = dev.model or mac end
    if data.brand then dev.brand = data.brand end
    if data.brand_display then dev.brand_display = data.brand_display end
    write_cfg(cfg)
    luci.http.write(cjson.stringify({ok = true, name = dev.name, brand = dev.brand}))
end

-- ─── send_cmd（写命令到文件，后台服务毫秒级执行）─────────────────
function send_cmd(cmd)
    -- cmd 格式: send <power> <mode> <temp> <fan> [mac]
    local parts = {}
    for p in string.gmatch(cmd, "%S+") do
        table.insert(parts, p)
    end
    if #parts < 5 then
        luci.http.write(cjson.stringify({ok = false, error = "参数不足"}))
        return
    end
    local power = parts[2]
    local mode = parts[3]
    local temp = tonumber(parts[4]) or 26
    local fan = parts[5]
    local mac = parts[6] or ""

    -- 未传 mac 则从 config 读取当前设备
    if mac == "" then
        local cfg = read_cfg()
        if cfg then
            mac = cfg.current_device_mac or ""
        end
    end
    if mac == "" then
        luci.http.write(cjson.stringify({ok = false, error = "未选择设备"}))
        return
    end

    local data = {
        mac = mac, power = power, mode = mode,
        temp = math.floor(temp), fan = fan,
    }
    local raw = cjson.stringify(data)
    local f = io.open("/tmp/acnexus_cmd.json", "w")
    if f then f:write(raw); f:close() end

    -- 清理旧结果
    os.remove("/tmp/acnexus_result.json")

    luci.http.write(cjson.stringify({ok = true, queued = true}))
end

-- ─── cmd_result（前端轮询命令结果）───────────────────────────────
function cmd_result()
    local f = io.open("/tmp/acnexus_result.json", "r")
    if f then
        local raw = f:read("*all"); f:close()
        luci.http.write(raw)
    else
        luci.http.write(cjson.stringify({ok = false, pending = true}))
    end
end

-- ─── save_schedule ─────────────────────────────────────────────
function save_schedule(cmd)
    -- cmd 格式: save_schedule <b64 JSON>
    local b64 = string.sub(cmd, 15)
    local raw = b64decode(b64)
    if not raw or raw == "" then luci.http.write(cjson.stringify({ok = false})); return end
    local ok, data = pcall(cjson.parse, raw)
    if not ok then luci.http.write(cjson.stringify({ok = false})); return end

    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end
    local mac = data.mac or cfg.current_device_mac or ""
    local _, dev = find_device(cfg, mac)
    if not dev then
        dev = {}
        cfg.devices = cfg.devices or {}
        cfg.devices.broadlink = cfg.devices.broadlink or {}
        cfg.devices.broadlink[mac] = dev
    end
    if data.templates then cfg.schedule_templates = data.templates end
    if data.active_template then dev.active_template = data.active_template end
    if data.schedule_enabled ~= nil then dev.schedule_enabled = data.schedule_enabled end
    if data.auto_adjust ~= nil then dev.auto_adjust = data.auto_adjust end
    write_cfg(cfg)
    luci.http.write(cjson.stringify({ok = true}))
end

-- ─── save_rules ────────────────────────────────────────────────
function save_rules(cmd)
    local b64 = string.sub(cmd, 12)
    local raw = b64decode(b64)
    if not raw or raw == "" then luci.http.write(cjson.stringify({ok = false})); return end
    local ok, data = pcall(cjson.parse, raw)
    if not ok then luci.http.write(cjson.stringify({ok = false})); return end

    local cfg = read_cfg()
    if not cfg then luci.http.write(cjson.stringify({ok = false})); return end
    local mac = data.mac or cfg.current_device_mac or ""
    local _, dev = find_device(cfg, mac)
    if dev then
        dev.temp_rules = data.rules or {}
        write_cfg(cfg)
    end
    luci.http.write(cjson.stringify({ok = true}))
end

-- 列出所有有日志的日期（纯 Lua，不走 Python 冷启动）
function log_dates()
    local dir = "/root/.ac_controller/logs"
    local dates = {}
    local p = io.popen("ls -1tr " .. dir .. "/*.md 2>/dev/null | sed 's|.*/||; s|\\.md$||'")
    if p then
        for line in p:lines() do
            if line ~= "" then
                table.insert(dates, 1, line)  -- ls -1tr 是时间升序，前端要降序
            end
        end
        p:close()
    end
    luci.http.prepare_content("application/json")
    luci.http.write(cjson.stringify({ok = true, dates = dates}))
end

function log_download()
    -- 日志下载单独走一个 endpoint，绕开 luci.sys.exec 的 4KB 截断
    local date_str = luci.http.formvalue("date") or ""
    -- 安全校验：YYYY-MM-DD
    if not string.match(date_str, "^%d%d%d%d%-%d%d%-%d%d$") then
        luci.http.status(400, "Bad Request")
        luci.http.prepare_content("text/plain; charset=utf-8")
        luci.http.write("非法日期格式")
        return
    end
    local f = io.open("/root/.ac_controller/logs/" .. date_str .. ".md", "r")
    if not f then
        luci.http.status(404, "Not Found")
        luci.http.prepare_content("text/plain; charset=utf-8")
        luci.http.write("日志不存在: " .. date_str)
        return
    end
    local content = f:read("*all")
    f:close()
    luci.http.header("Content-Type", "text/markdown; charset=utf-8")
    luci.http.header("Content-Disposition", 'attachment; filename="acnexus-' .. date_str .. '.md"')
    luci.http.write(content)
end

function download_guide()
    local f = io.open("/usr/share/acnexus/docs/guide.md", "r")
    if not f then
        luci.http.status(404, "Not Found")
        luci.http.prepare_content("text/plain; charset=utf-8")
        luci.http.write("文档不存在")
        return
    end
    local content = f:read("*all")
    f:close()
    luci.http.header("Content-Type", "text/markdown; charset=utf-8")
    luci.http.header("Content-Disposition", "attachment; filename=\"AC-Nexus-OpenWRT-使用指南.md\"")
    luci.http.write(content)
end
