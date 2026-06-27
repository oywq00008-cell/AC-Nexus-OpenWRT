local m, s, o

m = Map("acnexus", "AC-Nexus-OpenWRT",
    "AI 智能空调控制器 · Broadlink RM + 米家MIoT红外遥控器")

function m.on_commit(self)
    -- Lua 版 UCI → config.json 双向同步（无 Python 冷启动延迟）
    local cjson = require "luci.jsonc"
    local cfg_path = "/root/.ac_controller/config.json"

    -- 1. 读取 UCI（兼容 acnexus.settings 旧路径 + @acnexus[0] CBI 路径）
    local uci = {}
    local p = io.popen("uci show acnexus 2>/dev/null")
    local uci_out = p and p:read("*a") or ""
    -- 修复：(%[%d+%])? 正确匹配 @acnexus[0] bracket 格式；原写法 [?%d*%] 是字符类永远无法匹配
    for line in uci_out:gmatch("[^\n]+") do
        local key, val = line:match("^acnexus%.[@%w]+(%[%d+%])?%.([^=]+)=(.+)$")
        if key then
            uci[key] = val:match("^'([^']*)'$") or val:match('^"([^"]*)"$') or val
        end
    end

    -- 2. 读取 config.json
    local cfg = {}
    local f = io.open(cfg_path, "r")
    if f then
        local ok, decoded = pcall(cjson.parse, f:read("*a"))
        if ok then cfg = decoded end
        f:close()
    end

    -- 3. 同步全局设置 (UCI → config)，同时记录变更以精准清除缓存
    local old_weather = cfg.weather_provider
    local old_typhoon = cfg.typhoon_provider
    local old_loc_lat, old_loc_lon = (cfg.location or {}).lat, (cfg.location or {}).lon
    local old_enabled = cfg.enabled

    cfg.api_key = uci.api_key or cfg.api_key or ""
    cfg.qw_host = uci.qw_host or cfg.qw_host or ""
    cfg.baidu_key = uci.baidu_key or cfg.baidu_key or ""
    cfg.weather_provider = uci.weather_provider or cfg.weather_provider or "qweather"
    cfg.typhoon_provider = uci.typhoon_provider or cfg.typhoon_provider or "nmc"
    -- Flag: 取消勾选时 UCI 删除该行 → 视为 false
    -- 直接读 UCI 确保可靠（不依赖正则解析，兼容 acnexus.settings 旧格式）
    local p_en = io.popen("uci -q get acnexus.@acnexus[0].enabled 2>/dev/null || uci -q get acnexus.settings.enabled 2>/dev/null")
    local raw_en = p_en and p_en:read("*a"):gsub("%s+", "") or ""
    if p_en then p_en:close() end
    cfg.enabled = (raw_en == "1")
    local p_ty = io.popen("uci -q get acnexus.@acnexus[0].typhoon_ac_off 2>/dev/null || uci -q get acnexus.settings.typhoon_ac_off 2>/dev/null")
    local raw_ty = p_ty and p_ty:read("*a"):gsub("%s+", "") or ""
    if p_ty then p_ty:close() end
    cfg.typhoon_ac_off = (raw_ty == "1")
    -- weather_provider_set 不在 CBI 表单中，仅在 UCI 明确存在 "1" 时才设为 true
    if uci.weather_provider_set then
        cfg.weather_provider_set = (uci.weather_provider_set == "1")
    end

    -- 位置
    cfg.location = cfg.location or {}
    local new_lat = uci.location_lat and tonumber(uci.location_lat)
    local new_lon = uci.location_lon and tonumber(uci.location_lon)
    if new_lat then cfg.location.lat = new_lat end
    if new_lon then cfg.location.lon = new_lon end
    if uci.location_name then cfg.location.name = uci.location_name end

    -- 判断变更范围
    local weather_changed = (uci.weather_provider and uci.weather_provider ~= old_weather)
    local typhoon_changed = (uci.typhoon_provider and uci.typhoon_provider ~= old_typhoon)
    local loc_changed = (new_lat and new_lat ~= old_loc_lat) or (new_lon and new_lon ~= old_loc_lon)

    -- 4. 同步博联设备 (UCI → config)
    cfg.devices = cfg.devices or {}
    cfg.devices.broadlink = type(cfg.devices.broadlink) == "table" and cfg.devices.broadlink or {}
    cfg.devices.xiaomi_cloud = cfg.devices.xiaomi_cloud or {}

    -- 解析 UCI device 节 → {[mac] = {name, host, port}}
    local uci_devs = {}
    for line in uci_out:gmatch("[^\n]+") do
        local sec, k, v = line:match("^(acnexus%.@device%[%d+%])%.(%w+)='([^']*)'$")
        if sec and k and v then
            uci_devs[sec] = uci_devs[sec] or {}
            uci_devs[sec][k] = v
        end
    end

    for _, dev in pairs(uci_devs) do
        local mac = dev.mac
        -- 过滤空 mac 占位模板（UCI @device[0] 的 mac=''），不同步到运行时 config.json
        -- 与 acnexus_api.py 的 _uci_set_device 守卫对齐（Python: if not mac: return）
        if mac and mac ~= "" then
            local existing = cfg.devices.broadlink[mac] or {}
            if not existing.name or existing.name == "" then
                existing.name = dev.name or existing.model or mac
            end
            if dev.name then existing.name = dev.name end
            if dev.host then existing.host = dev.host end
            if dev.port then existing.port = dev.port end
            existing.mac = mac
            existing.brand = existing.brand or "gree"
            cfg.devices.broadlink[mac] = existing
        end
    end

    -- 5. 原子写入
    os.execute("mkdir -p " .. cfg_path:match("^(.*)/"))
    local tmp_path = cfg_path .. ".tmp"
    local out = io.open(tmp_path, "w")
    if out then
        local s = cjson.stringify(cfg, true)
        -- 修复 Lua cjson 将空 table {} 序列化为 [] 的问题
        -- 与 controller/acnexus.lua 的 write_cfg 后处理对齐
        local devs = cfg.devices or {}
        for provider in pairs(devs) do
            s = s:gsub('("' .. provider .. '"%s*:%s*)%[%]', '%1{}')
        end
        s = s:gsub('("schedule_templates"%s*:%s*)%[%]', '%1{}')
        out:write(s)
        out:close()
        os.rename(tmp_path, cfg_path)
    end
    -- 6. 精准清除缓存
    if weather_changed or loc_changed then
        os.execute("rm -f /tmp/acnexus_weather.json 2>/dev/null")
    end
    if typhoon_changed or loc_changed then
        os.execute("rm -f /tmp/acnexus_typhoon.json 2>/dev/null")
    end
    -- 清除 LuCI 缓存
    os.execute("rm -f /tmp/luci-indexcache*")

    -- 7. 修复：enabled 状态变更时显式重启服务（绕过 procd 生命周期断裂）
    if cfg.enabled ~= old_enabled then
        if cfg.enabled then
            os.execute("/etc/init.d/acnexus start 2>/dev/null &")
        else
            os.execute("/etc/init.d/acnexus stop 2>/dev/null &")
        end
    end
end

-- ═══ 全局设置 ═══
s = m:section(TypedSection, "acnexus", "全局设置")
s.anonymous = true
s.addremove = false

o = s:option(Value, "api_key", "和风天气 API Key")
o.password = true
o = s:option(Value, "qw_host", "和风天气 Host")
o.datatype = "host"
o = s:option(Value, "baidu_key", "百度天气 API Key")
o.password = true
o.rmempty = true
o = s:option(ListValue, "weather_provider", "天气数据源")
o:value("qweather", "和风天气"); o:value("baidu", "百度天气")

o = s:option(Value, "location_lat", "纬度")
o.datatype = "float"
o = s:option(Value, "location_lon", "经度")
o.datatype = "float"
o = s:option(Value, "location_name", "位置名称")

o = s:option(ListValue, "typhoon_provider", "台风数据源")
o:value("nmc", "中央气象台 (西北太平洋)"); o:value("nhc", "NHC (北大西洋飓风)")
o = s:option(Flag, "typhoon_ac_off", "风暴临近自动关闭空调")

o = s:option(Flag, "enabled", "启用服务（总开关）")

return m
