# 📖 功能详情 (Feature Reference)

> **版本**: v3.1
> **范围**: AC-Nexus-OpenWRT OpenWRT 路由器端插件
> **目标读者**: 想深入了解每个功能的工作原理 / 配置项 / 边界条件的用户

---

## 目录

1. [天气数据（双源 + 智能回退）](#1-天气数据)
2. [台风监测（< 100km 强制关空调）](#2-台风监测)
3. [定时任务（开机/关机/规则）](#3-定时任务)
4. [自动调温（2h 相对间隔）](#4-自动调温)
5. [UCI 配置双向同步](#5-uci-配置双向同步)
6. [LuCI 控制面板](#6-luci-控制面板)
7. [日志系统（每日文件 + 下载）](#7-日志系统)
8. [Service 守护（procd + 异常降级）](#8-service-守护)
9. [设备管理（扫描 + 下拉切换）](#9-设备管理)
10. [红外协议（自研 + hvac_ir）](#10-红外协议)

---

## 1. 天气数据（双源 + 智能回退）

### 1.1 数据源

| Provider | URL | 鉴权字段 | 适用场景 |
|----------|-----|----------|----------|
| **百度** | `api.map.baidu.com/weather/v1/?data_type=now` | `baidu_key` | 国内首选，免费 5000 次/天 |
| **和风** | `QW_HOST/v7/weather/now` | `api_key` + `qw_host` | 备选，免费 50000 次/月 |

### 1.2 回退策略

```
fetch_weather() 决策树:

[用户配置: weather_provider]
  ├─ "baidu" (默认)
  │   ├─ 调百度 → 成功?
  │   │   ├─ YES → 返回百度结果 ✅
  │   │   └─ NO → [检查 weather_provider_set]
  │   │       ├─ True (用户显式选) → 返回 None (不偷回落) ⚠️
  │   │       └─ False (默认) → 回落和风
  │   │           ├─ 成功 → 返回和风 ✅
  │   │           └─ 失败 → 兜底 _last_weather 旧缓存 🔄
  └─ "qweather" (显式选和风)
      └─ 直接调和风
          ├─ 成功 → 返回 ✅
          └─ 失败 → 兜底 _last_weather 旧缓存 🔄
```

### 1.3 缓存策略

| 缓存类型 | 更新时机 | 用途 |
|----------|----------|------|
| `_cfg._cached_temp` | 每次 `fetch_weather` 成功 | 自动调温 / 当前温度显示 |
| `_last_weather` | weather_loop 拉到新数据 | 双源失败兜底 |

### 1.4 触发时机

- **service 启动**：`init()` 末尾立即拉一次（避免 daemon 起来时空数据）
- **30min 巡检**：`_weather_loop` daemon
- **手动刷新**：status API `force=true`

### 1.5 日志

- 成功：`[HH:MM] 获取成功: 24°C 湿度 43%`
- 失败：`[HH:MM] 拉取失败: <错误信息>`
- 无 key：`[百度实况] 无 baidu_key, 跳过 → 回落和风`（仅 stdout/procd syslog）

### 1.6 边界条件

| 场景 | 行为 |
|------|------|
| 百度和风都没填 key | 都返 None，UI 显示 `--` |
| 百度 key 过期 | 回落和风（如果和风能用）|
| 和风 host 错（`QW_HOST=""`）| 走和风路径立即失败 → 兜底旧缓存 |
| 网络断开 | 走 try/except，返 None 或旧缓存 |
| `_last_weather` 也没值 | 返 None，UI 显示 `--`（**最差情况**）|

---

## 2. 台风监测（< 100km 强制关空调）

### 2.1 数据源

- **NMC（中央气象台）**：`weather.cma.cn/web/typhoon/...` 公开数据
- 30min 拉一次，写入 `_ty_cache`（模块级全局）

### 2.2 数据结构

```python
_ty_cache: list = [
    {
        "id": "T2024-06",          # NMC 台风 ID
        "cn": "烟花",              # 中文名
        "eng": "In-Fa",           # 英文名
        "cat": "台风",             # 强度等级
        "detail": {                # fetch_typhoon_detail 拉的详情
            "lat": 22.5,           # 当前纬度
            "lon": 114.3,          # 当前经度
            "cn": "烟花",          # 冗余便于 typhoon_threat_distance 读
            "eng": "In-Fa",
            "cat": "台风",
        }
    },
    ...
]
```

### 2.3 拦截链（核心安全策略）

```
触发场景 + distance 检查:

┌─────────────────────────────────────────────────────┐
│ 30min 台风巡检 (_typhoon_loop)                       │
│   min_dist = calc_distance(loc, storm.loc)          │
│   IF min_dist < 100 AND typhoon_ac_off=True:         │
│     → 强制发关 ❌  (不查 power, 不查 ty_ac_off_sent)  │
│   ELSE:                                              │
│     → 跳过                                           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 定时开机 (scheduled_job at "12:00")                  │
│   IF distance < 100:                                │
│     → 跳过 (信任 30min 巡检已强制关过)                │
│   ELSE:                                              │
│     → 正常跑发码                                    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 定时关机 (scheduled_off_job at "22:00")              │
│   IF distance < 100:                                │
│     → 跳过 (避免和台风抢发)                          │
│   ELSE:                                              │
│     → 正常跑发关                                    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 自动调温 (auto_adjust_job every 2h)                  │
│   IF distance < 100:                                │
│     → 跳过 (30min 巡检会强制关, 这里是反行为)        │
│   ELIF power=off:                                    │
│     → 跳过 (用户主动关了不打扰)                      │
│   ELIF mode/temp 一致:                               │
│     → 跳过 (不发码, 节能)                            │
│   ELSE:                                              │
│     → 跑规则发码                                    │
└─────────────────────────────────────────────────────┘
```

### 2.4 距离计算

- `calc_distance(lat1, lon1, lat2, lon2)` 用 Haversine 公式，返回 km
- 输入：用户位置（`cfg.location`）vs 台风当前位置
- 输出：球面距离，0km = 同一坐标

### 2.5 触发发关的条件（AND 全部满足）

1. `typhoon_ac_off=True`（CBI 设置，默认开）
2. `min_dist < 100`（km）
3. 设备在线（`_online_macs` 为空 OR mac 在列表中）

### 2.6 发关动作

```python
for mac, dev in devices.items():
    if not is_online(mac): continue
    send_ac("off", "cool", 26, "auto", source="台风", mac=mac)
    write_log("空调", f"[{HH:MM}] 台风自动关机")
```

**故意写两条日志**（`send_ac` 内部一条 + `judge_and_shutdown` 一条），让 `get_last_ac_state` 的日志解析规则能匹配到 OFF_WORDS。

### 2.7 CBI 设置项

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| `typhoon_ac_off` | bool | True | < 100km 时是否自动关 |
| `typhoon_provider` | str | `nmc` | 暂未启用桌面端的 NHC 切换 |

### 2.8 安全设计意图（用户明确）

> 台风 < 100km 已进入核心圈，外机可能被大风吹倒倒转烧毁
> 雷电也可能对运行中的空调硬件造成雷击损毁
> 用户若坚持要开空调，必须手动去 CBI 设置页关闭 `typhoon_ac_off`
> 台风来时沿海城市根本不会热，开风扇足矣

### 2.9 边界条件

| 场景 | 行为 |
|------|------|
| 30min 拉失败 | `_ty_cache` 保留上次的（不会清空），`typhoon_threat_distance` 仍能用 |
| 30min 拉成功但无活跃台风 | `_ty_cache = []`，`min_dist` 保持 99999 |
| 设备离线 | 跳过该设备，但继续发其他在线设备 |
| 多个台风同时 < 100km | 取最近的一个发关（min 函数）|

---

## 3. 定时任务（开机/关机/规则）

### 3.1 任务类型

| 任务 | 触发 | 作用 | 拦截条件 |
|------|------|------|----------|
| `scheduled_job` | 每天 `trigger_time` | 开机 + 跑温度规则 | < 100km 跳过 |
| `scheduled_off_job` | 每天 `off_time` | 发关 | < 100km 跳过 |
| `auto_adjust_job` | 每 2h 相对间隔 | 跑温度规则（不开机）| < 100km / power=off / mode-temp 一致 跳过 |

### 3.2 schedule 库配置

```python
# register_all_jobs() 在 scheduler_loop 启动时调一次
sch.clear()
for mac, dev in config["devices"].items():
    if dev.get("schedule_enabled", True):
        sch.every().day.at(dev.get("trigger_time", "12:00")).do(scheduled_job, mac=mac)
    if dev.get("off_enabled"):
        sch.every().day.at(dev.get("off_time", "22:00")).do(scheduled_off_job, mac=mac)
    if dev.get("auto_adjust", True):
        sch.every(2).hours.do(auto_adjust_job, mac=mac)  # 相对间隔
```

### 3.3 精确睡眠（不是固定 setInterval）

```python
def scheduler_loop():
    register_all_jobs()
    while True:
        with _sched_lock:
            sch.run_pending()   # 触发所有到期任务
        idle = sch.idle_seconds()  # 下一个 job 距现在多少秒
        sleep_sec = max(idle, 0) if idle is not None else 15
        time.sleep(sleep_sec)
```

- `idle_seconds()` 返回**精确**等待时间（库自动维护 `last_run`）
- 三类任务**共用**一个 schedule 库，**共用** scheduler_loop
- `auto_adjust_job` 关机时提前 return，循环时间照常推进（用户要求）

### 3.4 任务增删后重注册

`acnexus_api.py` 在以下三处末尾调 `re_register()`（在 `_sched_lock` 内）：
- `discover` 命令（新设备）
- `save_device` 命令（字段变化）
- `save_schedule` 命令（trigger_time 改了）

不重注册的话，schedule 库永远只跑**启动时**的设备列表。

### 3.5 温度规则（默认 6 条）

```json
{
  "rules": [
    {"max": 99, "min": 36, "mode": "cool", "temp": 24},
    {"max": 35, "min": 33, "mode": "cool", "temp": 25},
    {"max": 32, "min": 30, "mode": "cool", "temp": 26},
    {"max": 29, "min": 25, "mode": "cool", "temp": 27},
    {"max": 24, "min": 18, "mode": "off",  "temp": 0},
    {"max": 17, "min": 0,  "mode": "heat", "temp": 28}
  ]
}
```

`decide_ac(outdoor_temp, mac)` 倒序遍历找第一个匹配区间，返回 `(target_temp, mode)`。

### 3.6 边界条件

| 场景 | 行为 |
|------|------|
| 多设备各设不同 trigger_time | 每台独立 schedule job |
| trigger_time 未设置 | 默认 12:00 |
| off_time 未设置 | off_enabled 默认 False，不注册 |
| 规则列表为空 | `decide_ac` 不发码（默认 off=关机）|
| 自动调温时空调已关 | 跳过不发码（等下一次开机/定时）|

---

## 4. 自动调温（2h 相对间隔）

### 4.1 设计意图

> 用户活动 24h 不规律（有人 6 点起床、有人 14 点活动、有人凌晨加班），
> 用 `sch.every(2).hours` 相对间隔，**开机后 2h 调一次**，自然贴合空调使用场景

### 4.2 决策树

```
auto_adjust_job(mac):
  IF device offline: 跳过
  IF distance < 100km: 跳过 (台风保护)
  IF power=off (读 get_last_ac_state): 跳过 (不打扰用户)
  outdoor = _cfg._cached_temp or fetch_weather()
  IF fetch failed: 跳过
  target, mode = decide_ac(outdoor)
  IF mode == "off":
    send_ac("off", ...)  # 写入"自动调温 → 关机"日志
  ELIF state.mode==mode AND state.temp==target:
    write_log("空调", "[HH:MM] 自动调温 → 不更改温度")
    # 不发码
  ELSE:
    send_ac("on", mode, target, "auto", source="自动")
```

### 4.3 相对间隔 vs 绝对整点

| 方案 | 用户体验 | 适用场景 |
|------|----------|----------|
| `every(2).hours`（相对）| 开机后 2h、4h、6h... | ✅ 全天不规律活动 |
| `every().day.at("12:00,14:00,16:00,18:00,20:00")` | 每天固定 5 个整点 | ❌ 替用户决定作息（已撤回）|

### 4.4 跳过场景汇总

| 跳过原因 | 日志 |
|----------|------|
| 设备离线 | `🔄 [客厅] 自动调温 → 设备离线，跳过` |
| 距离 < 100km | `🔄 [客厅] 自动调温: 风暴 烟花 距 60km，跳过` |
| 空调 power=off | （不写日志）|
| 天气拉失败 | `🔄 [客厅] 自动调温: 天气获取失败，跳过` |
| mode/temp 一致 | `[HH:MM] [客厅] 自动调温 → 不更改温度` |
| mode=off（规则匹配）| `[HH:MM] 空调操作: ...` (send_ac 内部写) |

---

## 5. UCI 配置双向同步

### 5.1 双向同步矩阵

| 触发方向 | 路径 | 同步内容 |
|----------|------|----------|
| CBI → UCI | CBI 设置页保存 | `config.broadlink.*` UCI sections 写入 |
| UCI → config.json | service `init()` 启动时 | 从 `uci show acnexus` 读所有字段到 `cfg.config` |
| config.json → UCI | CBI 不直接改 config.json（用 CBI 设置页）| 仅 `save_device` 时同步单条 device |
| 弹窗 → config.json | dashboard 弹窗保存 | 直接写 JSON，不走 UCI |
| 弹窗 → UCI | 同上 | status API 末尾读 config.json 同步到 UCI（防 CBI 页面读到旧值）|

### 5.2 关键字段

#### UCI 字段（`/etc/config/acnexus`）

```uci
config acnexus 'main'
    option enabled '1'
    option api_key 'YOUR_QWEATHER_KEY'
    option qw_host 'https://api.qweather.com'
    option baidu_key 'YOUR_BAIDU_KEY'
    option weather_provider 'baidu'
    option weather_provider_set '0'
    option typhoon_ac_off '1'
    option typhoon_provider 'nmc'
    option location_lat '22.5429'
    option location_lon '114.0596'
    option location_name '深圳'

config device 'device_e870723f41ee'
    option mac 'e870723f41ee'
    option name '客厅'
    option brand 'gree'
    option host '192.168.1.100'
    option port '80'
```

#### config.json 字段（`/root/.ac_controller/config.json`）

```json
{
  "enabled": true,
  "api_key": "YOUR_QWEATHER_KEY",
  "qw_host": "https://api.qweather.com",
  "baidu_key": "YOUR_BAIDU_KEY",
  "weather_provider": "baidu",
  "weather_provider_set": false,
  "typhoon_ac_off": true,
  "typhoon_provider": "nmc",
  "location": {"lat": 22.5429, "lon": 114.0596, "name": "深圳"},
  "current_device_mac": "e870723f41ee",
  "devices": {
    "e870723f41ee": {
      "name": "客厅",
      "brand": "gree",
      "host": "192.168.1.100",
      "port": 80,
      "schedule_enabled": true,
      "trigger_time": "12:00",
      "off_enabled": true,
      "off_time": "22:00",
      "auto_adjust": true,
      "temp_rules": [...]
    }
  }
}
```

### 5.3 UCI 路径硬编码修复（v3.1）

`config.py` 之前用 `Path.home() / ".ac_controller"`，**uhttpd CGI 进程以 nobody 运行**，`Path.home()` 解析为 `/var` 导致 service 写日志和 CGI 读路径分裂。

v3.1 硬编码 `Path("/root/.ac_controller")`（OpenWrt 上），同时修 `acnexus_api.py` 5 处 `os.path.expanduser("~/.ac_controller/...")`。

### 5.4 `enabled` 字段特殊处理

CBI `Flag='0'` **取消勾选会删除 UCI 行**（不写 `'0'`），所以 UCI 同步时需检测：

```python
# 反向同步 config.json ← UCI
if 'enabled' not in uci:  # 字段缺失 = 取消勾选
    cfg.enabled = False
else:
    cfg.enabled = uci['enabled'] == '1'
```

---

## 6. LuCI 控制面板

### 6.1 入口

- URL：`http://<router-ip>/cgi-bin/luci/admin/services/acnexus`
- 注册文件：`/usr/lib/lua/luci/controller/broadlink.lua`

### 6.2 路由表

| Path | Function | 用途 |
|------|----------|------|
| `/admin/services/acnexus` | alias → dashboard | 父入口 |
| `/admin/services/acnexus/dashboard` | template() | 主控制面板 |
| `/admin/services/acnexus/settings` | cbi() | CBI 设置页（启用服务/API key/台风开关）|
| `/admin/services/acnexus/api` | call("api") | API 命令路由（4KB 截断）|
| `/admin/services/acnexus/log_download` | call("log_download") | 日志下载独立 endpoint |

### 6.3 Dashboard 布局

```
┌──────────────────────────────────┐
│ 🎮 AC-Nexus-OpenWRT 控制面板            │
│ ┌──────────┐ ┌──────────────────┐│
│ │ [设备▼] │ │ [📋] [⏰] [⚙️] [🔄] ││  ← 工具栏
│ └──────────┘ └──────────────────┘│
├──────────────────────────────────┤
│ 🏠 客厅 RM4 mini                  │
│ 在线 | MAC e870723f41ee            │
├──────────────────────────────────┤
│  室温        室外      模式       │  ← ac-info-row
│  26°C       24°C      cool        │
├──────────────────────────────────┤
│ [🔌][❄][🔥][💧][💨]               │  ← 5 个按钮
│ 电源 制冷 制热 除湿 送风          │
├──────────────────────────────────┤
│       ┌─────┐                    │
│       │  ▶  │                    │  ← 大圆按钮（发送所有设置）
│       └─────┘                    │
├──────────────────────────────────┤
│ ▼ 状态消息（3 秒后自动消失）        │
└──────────────────────────────────┘
```

### 6.4 按钮语义

| 按钮 | 行为 | 触发 API |
|------|------|----------|
| 电源 / 制冷 / 制热 / 除湿 / 送风 | **只更新 UI 状态，不发码** | （无 API）|
| 大圆 `▶` 按钮 | **发码**：把当前 power+mode+temp+fan 一起发 | `send` |
| 📋 日志 | 弹窗选日期下载 | `log_dates` + `/log_download?date=...` |
| ⏰ 定时 | 弹窗调温度规则 + 定时开关 | `save_schedule` |
| ⚙️ 设备 | 弹窗显示设备名/品牌/host，保存 | `save_device` |
| 🔄 刷新 | 强制拉所有数据 | `status force=true` |

### 6.5 API 列表（dashboard 调）

| cmd | 功能 | 返回 |
|-----|------|------|
| `status` | 读所有状态（缓存优先，缺才现场拉）| `{online, state, weather, typhoon, ...}` |
| `refresh [force=true]` | 强制拉天气+台风+judge | `{ok}` |
| `discover` | 局域网扫描 Broadlink RM | `{devices: [{mac,name,host,port}]}` |
| `send_ac <base64>` | 发空调指令 | `{ok, result}` |
| `save_device <base64>` | 保存设备名/品牌 | `{ok}` |
| `save_schedule <base64>` | 保存定时+温度规则 | `{ok}` |
| `search_location <q>` | Nominatim 城市搜索 | `[{lat,lon,name,display_name}]` |
| `log_dates` | 列出有日志的日期 | `["2026-06-09", ...]` |
| `log_download <base64>` | 下载指定日期的 .md | （直接 stream 走独立 endpoint）|

### 6.6 主题适配

- 自动跟随系统 dark/light（CSS `@media (prefers-color-scheme)`）
- 移动端：`max-width: 480px` 容器自动收缩，触摸目标 ≥44px

---

## 7. 日志系统（每日文件 + 下载）

### 7.1 文件位置

`/root/.ac_controller/logs/YYYY-MM-DD.md`

每天一个文件，UTF-8 编码，Markdown 表格格式。

### 7.2 格式

```markdown
# 2026-06-09 操作日志

## 🎮 空调操作
| 时间 | 内容 |
|------|------|
| 10:30 | [10:30] 手动开机 → 制冷 26°C |
| 12:00 | [12:00] 定时开机 → 制冷 24°C |
| 14:30 | [14:30] 自动调温 → 不更改温度 |
| 15:00 | [15:00] 台风自动关机 |

## 🌤️ 天气
| 时间 | 内容 |
|------|------|
| 10:00 | [10:00] 获取成功: 24°C 湿度 43% |
| 10:10 | [10:10] 拉取失败: timeout |

## 🌀 台风监测
| 时间 | 内容 |
|------|------|
| 12:00 | [12:00] 烟花 (In-Fa) 台风 距60km |
| 12:00 | [12:00] 台风自动关机 |

## ⚙️ 系统
| 时间 | 内容 |
|------|------|
| 10:00 | [10:00] 设备扫描: 找到 1 台 RM4 mini |
| 10:01 | [10:01] ⏰ [客厅] 定时触发: 室外 24°C → 制冷 |
```

### 7.3 4 个分类

| 分类 | 触发函数 | 用途 |
|------|----------|------|
| 🎮 空调操作 | `send_ac` 内部 + `judge_and_shutdown` | `get_last_ac_state` 解析对象 |
| 🌤️ 天气 | 天气 loop 成功/失败 | 排障 |
| 🌀 台风 | `judge_and_shutdown` 巡检 | 排障 |
| ⚙️ 系统 | 设备扫描 / 定时触发 / 自动调温 | 排障 |

### 7.4 日志下载流程

```
dashboard 工具栏 → 点 📋
  → 弹窗 fillLogForm()
    → API 'log_dates' → 拿 ['2026-06-09', '2026-06-08', ...]
    → 渲染 14 天日期网格
      → 有日志的 .has-log class 红色边框
  → 用户点红色日期 → 选中状态 .selected
  → 点 "⬇ 下载日志" → window.open('/log_download?date=...')
    → controller.lua log_download()
      → 校验 YYYY-MM-DD 正则
      → 读 /root/.ac_controller/logs/<date>.md
      → 设置 Content-Disposition: attachment
      → 输出文件内容
    → 浏览器弹下载框
```

### 7.5 关键设计：`get_last_ac_state`

```python
def get_last_ac_state():
    """倒序遍历今日日志 🎮 分类，找最近一次 [HH:MM] 开/关机操作
    返回 {"power": "on"|"off", "mode": "cool", "temp": 26, "ts": "14:30"}"""
```

**特殊关键字匹配**（OFF_WORDS）：
```python
OFF_WORDS = ("手动关机", "定时关机", "自动关机", "台风自动关机", "关机")
ON_WORDS = ("手动开机", "定时开机", "自动", ...)  # 见源码
```

**双日志设计**（台风自动关机故意写两条）：
- `send_ac("off")` 内部写一条 → "空调操作"
- `judge_and_shutdown` 额外写一条 → "空调操作"
- `get_last_ac_state` 倒序遍历能找到**最近一条**包含 OFF_WORDS 的

### 7.6 边界条件

| 场景 | 行为 |
|------|------|
| 当日无日志 | 返 `{"power": "off", "mode": "cool", "temp": 26}`（默认）|
| 日志文件被删 | `get_log_dates` 跳过 |
| 日期格式非法 | log_download 返 400 Bad Request |
| 文件不存在 | log_download 返 404 Not Found |

---

## 8. Service 守护（procd + 异常降级）

### 8.1 procd 守护（`/etc/init.d/acnexus`）

```sh
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=90
STOP=15

start_service() {
    procd_open_instance
    procd_set_param command /usr/bin/python3 /usr/lib/acnexus/acnexus_service.py
    procd_set_param stdout 1    # syslog
    procd_set_param stderr 1    # syslog
    procd_set_param respawn 3600 5 5  # 1h 阈值, 失败 5 次退出
    procd_close_instance
}
```

### 8.2 启动流程

```
/etc/init.d/acnexus start
  → procd 拉起 acnexus_service.py
    → service 调 acnexus_core.init()
      → load_config()       # 读 /root/.ac_controller/config.json
      → _migrate_old_config()
      → _load_device_to_flat()
      → apply_config()      # UCI → config 同步
      → start_scheduler()   # 启动定时线程
      → start_data_loops()  # 启动 weather/typhoon daemon 线程
      → 立即拉一次天气/台风（首次）→ daemon 第一次 sleep 再拉
```

### 8.3 异常降级（v3.1 新增）

`init()` 整体包 try/except：

```python
try:
    config = load_config()
except Exception as e:
    # 用空 defaults 撑住
    config = {默认空配置}
    print(f"[init] load_config 失败, 降级运行: {e}")

try:
    _migrate_old_config()
except Exception as e:
    print(f"[init] _migrate_old_config 失败, 跳过: {e}")
    # 继续，不阻塞启动
# ... 启动调度 / 拉数据也各自 try/except
```

**目的**：service 任何步骤抛都不死，procd 不再反复刷 syslog。

### 8.4 日志输出

- `print()` / `sys.stderr.write()` → 走 procd 的 `procd_set_param stdout/stderr 1` → syslog
- `write_log("类别", "内容")` → 写当日 .md 文件（不走 syslog）

### 8.5 开机自启动

- `START=90`（靠后启动，依赖网络）
- `/etc/rc.d/S90acnexus` 软链自动创建

---

## 9. 设备管理（扫描 + 下拉切换）

### 9.1 扫描机制

`acnexus_api.py` 的 `discover` 命令：

```python
import broadlink
devices = broadlink.discover(timeout=2)  # 局域网 UDP 广播
# 返回 [{host, port, mac, ...}]
# 已知 devices 名字保留 (按 mac 匹配)
```

### 9.2 扫描结果

```json
{
  "ok": true,
  "devices": [
    {
      "mac": "e870723f41ee",
      "name": "客厅",            // 从已知 config 里继承
      "host": "192.168.1.100",
      "port": 80,
      "is_online": true
    }
  ]
}
```

### 9.3 已知设备名字保留

```python
# 扫描时不覆盖用户起的名字
if mac in cfg["devices"]:
    new_dev["name"] = cfg["devices"][mac].get("name", "")
```

### 9.4 首次打开自动扫描

如果 config.json `devices` 为空，dashboard 自动调 `discover`。
无设备时显示 6s 提示"自动扫描未发现设备"。

### 9.5 下拉切换

```javascript
// dashboard 设备下拉框
<select onchange="switchDevice(this.value)">
  <option value="e870723f41ee">客厅</option>
  <option value="...">主卧</option>
</select>

function switchDevice(mac) {
  api('switch_device ' + b64(mac))
    .then(() => loadAll(true));  // 重新拉所有数据
}
```

### 9.6 当前设备 MAC

存于 `cfg.config["current_device_mac"]`，所有发码 API 默认发这台。

---

## 10. 红外协议（自研 + hvac_ir）

### 10.1 支持品牌（17 种）

| 协议源 | 品牌 | 桌面端显示 | 路由器端 |
|--------|------|-----------|---------|
| hvac_ir | 格力 / 美的 / 海尔 / 奥克斯 / 海信 / 大金 / 三菱 / 松下 / 日立 / 富士通 / 巴鲁 / 开利 / 现代 / Fuego / 等 | ✅ | ✅ |
| **自研 protocols/** | **海尔 / 奥克斯 / 松下** | ✅ | ✅（路由器只这 3 个）|

### 10.2 自研协议原因

- hvac_ir 第三方库 14 个品牌
- **海尔 / 奥克斯 / 松下** 因早期 hvac_ir 编码/解析对部分型号有 bug，自研 3 个文件覆盖
- 路由器端只 `from haier import ...` / `from aux_ac import ...` / `from panasonic import ...`

### 10.3 发送协议统一接口

`ac_control.py:send_ac(power, mode, temp, fan, source=..., mac=...)`：

```python
def send_ac(power, mode, temp, fan, source="手动", mac=None):
    # 1. 找设备
    dev = get_device(mac)  # 读 cfg.devices[mac]
    brand = dev.get("brand", "gree")
    
    # 2. 映射字段
    pwr = sender.POWER_ON if power == "on" else sender.POWER_OFF
    fan_map = {"auto": ..., "1": ..., "2": ..., "3": ...,
               "low": FAN_1, "medium": FAN_2, "high": FAN_3}  # v3.1 加
    mode_map = {"cool": ..., "heat": ..., "dry": ..., "fan": ..., "off": ...}
    
    # 3. 动态 import
    sender = importlib.import_module(f"protocols.{brand}")
    # 海尔/奥克斯/松下 走自研 protocols/{haier,aux_ac,panasonic}.py
    # 其他品牌 走 hvac_ir
    
    # 4. 发码
    packet = sender.build_packet(pwr, mode, temp, fan)
    bl = broadlink.rm((host, port), mac)
    bl.send(packet)
    
    # 5. 写日志
    write_log("空调", f"[{HH:MM}] {source} {action} → {mode} {temp}°C")
```

### 10.4 边界条件

| 场景 | 行为 |
|------|------|
| 设备 brand 未设 | 默认 `gree`（hvac_ir）|
| 自研协议 import 失败 | 抛 ImportError → 写入日志，不发码 |
| 设备离线 | broadlink.rm 抛 ConnectionError → 写入"设备离线"日志 |
| hvac_ir 未装 | postinst 没装上 → sender 抛 ModuleNotFoundError |

---

## 附录 A：配置字段速查

| UCI 选项 | config.json key | 默认 | 说明 |
|----------|----------------|------|------|
| `enabled` | `enabled` | `1` | 总开关 |
| `api_key` | `api_key` | `""` | 和风 API key |
| `qw_host` | `qw_host` | `""` | 和风 host |
| `baidu_key` | `baidu_key` | `""` | 百度 key |
| `weather_provider` | `weather_provider` | `baidu` | 天气 provider |
| `weather_provider_set` | `weather_provider_set` | `0` | 用户是否显式选 |
| `typhoon_ac_off` | `typhoon_ac_off` | `1` | < 100km 自动关 |
| `typhoon_provider` | `typhoon_provider` | `nmc` | 台风 provider（暂只 NMC）|
| `location_lat` | `location.lat` | `39.90` | 北京默认 |
| `location_lon` | `location.lon` | `116.40` | 北京默认 |
| `location_name` | `location.name` | `Beijing` | 北京默认 |

## 附录 B：API 命令速查

| cmd | 用途 |
|-----|------|
| `status` | 读所有状态（缓存优先）|
| `refresh` 或 `refresh force=true` | 拉所有数据 |
| `discover` | 局域网扫描 |
| `send_ac <b64>` | 发空调 |
| `save_device <b64>` | 保存设备名/品牌 |
| `save_schedule <b64>` | 保存定时/温度规则 |
| `switch_device <b64>` | 切换当前设备 |
| `search_location <q>` | Nominatim 城市搜索 |
| `log_dates` | 列出有日志的日期 |
| `log_download <b64>` | 下载指定日期日志 |

## 附录 C：日志关键字（供排障 grep）

```bash
# 空调操作
grep "空调" ~/.ac_controller/logs/2026-06-09.md

# 台风
grep "台风" ~/.ac_controller/logs/2026-06-09.md

# 天气拉取失败
grep "拉取失败" ~/.ac_controller/logs/2026-06-09.md

# procd syslog
logread | grep -i broadlink
```

## 附录 D：手动调试清单

```bash
# 1. 状态
python3 /usr/lib/acnexus/acnexus_api.py status

# 2. 强制刷新
python3 /usr/lib/acnexus/acnexus_api.py refresh force=true

# 3. service 状态
/etc/init.d/acnexus status

# 4. procd 日志
logread | grep -i broadlink

# 5. 配置文件
cat /etc/config/acnexus
cat /root/.ac_controller/config.json | python3 -m json.tool

# 6. 今日日志
cat /root/.ac_controller/logs/$(date +%Y-%m-%d).md

# 7. 手动触发台风检查
python3 -c "
import sys; sys.path.insert(0, '/usr/lib/acnexus')
from acnexus_core.typhoon import typhoon_threat_distance
print(typhoon_threat_distance())
"
```
