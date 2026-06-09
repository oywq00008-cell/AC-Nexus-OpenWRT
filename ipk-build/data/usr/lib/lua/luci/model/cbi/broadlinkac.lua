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
o:value("gree", "格力"); o:value("midea", "美的"); o:value("haier", "海尔")
o:value("hisense", "海信"); o:value("hitachi", "日立"); o:value("daikin", "大金")
o:value("mitsubishi_heavy", "三菱重工"); o:value("mitsubishi", "三菱电机"); o:value("toshiba", "东芝")
o:value("panasonic", "松下"); o:value("sharp", "夏普"); o:value("fujitsu", "富士通")
o:value("aux", "奥克斯"); o:value("changhong", "长虹"); o:value("chigo", "志高")
o:value("tcl", "TCL"); o:value("xiaomi", "小米"); o:value("samsung", "三星")
o:value("lg", "LG"); o:value("whirlpool", "惠而浦")
o = s:option(Value, "host", "设备 IP 地址")
o.datatype = "ipaddr"
o = s:option(Value, "port", "端口")
o.datatype = "port"

-- 定时设置
o = s:option(Flag, "schedule_enabled", "启用定时开机")
o = s:option(Value, "trigger_time", "开机时间 (HH:MM)")
o = s:option(Flag, "off_enabled", "启用定时关机")
o = s:option(Value, "off_time", "关机时间 (HH:MM)")

-- 自动调温
o = s:option(Flag, "auto_adjust", "启用自动调温")

-- 温度规则 (3条)
o = s:option(Value, "rule_1_low", "规则1: 室外低温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_1_high", "规则1: 室外高温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_1_temp", "规则1: 目标温度 (°C)"); o.datatype = "range(16,30)"
o = s:option(ListValue, "rule_1_mode", "规则1: 模式")
o:value("cool", "制冷"); o:value("heat", "制热"); o:value("fan", "送风")

o = s:option(Value, "rule_2_low", "规则2: 室外低温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_2_high", "规则2: 室外高温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_2_temp", "规则2: 目标温度 (°C)"); o.datatype = "range(16,30)"
o = s:option(ListValue, "rule_2_mode", "规则2: 模式")
o:value("cool", "制冷"); o:value("heat", "制热"); o:value("fan", "送风")

o = s:option(Value, "rule_3_low", "规则3: 室外低温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_3_high", "规则3: 室外高温 (°C)"); o.datatype = "integer"
o = s:option(Value, "rule_3_temp", "规则3: 目标温度 (°C)"); o.datatype = "range(16,30)"
o = s:option(ListValue, "rule_3_mode", "规则3: 模式")
o:value("cool", "制冷"); o:value("heat", "制热"); o:value("fan", "送风")

return m
