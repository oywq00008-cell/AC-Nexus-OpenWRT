local m, s, o

m = Map("acnexus", "AC-Nexus-OpenWRT",
    "AI 智能空调控制器 · Broadlink RM + 小米红外遥控器")

function m.on_commit(self)
    -- 保存后同步 UCI → config.json（后台静默执行）
    os.execute("/usr/bin/python3 /usr/lib/acnexus/uci_sync.py 2>/dev/null &")
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

o = s:option(Flag, "enabled", "启用服务")

return m
