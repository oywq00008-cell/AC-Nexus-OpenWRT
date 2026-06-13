local m, s, o

m = Map("broadlinkac", "Broadlink AC",
    "AI 智能空调控制器 · Broadlink RM 系列")

-- ═══ 全局设置 ═══
s = m:section(TypedSection, "broadlinkac", "全局设置")
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
o = s:option(Flag, "typhoon_ac_off", "风暴 <100km 自动关空调")

o = s:option(Flag, "enabled", "启用服务")

-- ═══ 博联设备 ═══
s = m:section(TypedSection, "device", "博联设备 (RM红外遥控器)")
s.addremove = true
s.anonymous = true

o = s:option(Value, "name", "设备名称")
o = s:option(Value, "mac", "MAC 地址")
o.rmempty = false
o = s:option(ListValue, "brand", "空调品牌")
o:value("gree", "格力"); o:value("midea", "美的"); o:value("midea", "华凌"); o:value("midea", "小米"); o:value("haier", "海尔")
o:value("hisense", "海信"); o:value("hitachi", "日立"); o:value("daikin", "大金")
o:value("mitsubishi", "三菱"); o:value("panasonic", "松下"); o:value("fujitsu", "富士通")
o:value("aux_ac", "奥克斯"); o:value("ballu", "巴鲁"); o:value("carriermca", "开利")
o:value("hyundai", "现代"); o:value("fuego", "Fuego")
o = s:option(Value, "host", "设备 IP 地址")
o.datatype = "ipaddr"
o = s:option(Value, "port", "端口")
o.datatype = "port"

return m
