#!/usr/bin/env python3
"""AC-Nexus-OpenWRT 后台守护进程

一直运行，负责：
- 每 10 分钟拉天气 → 写 /tmp/acnexus_weather.json
- 每 30 分钟拉台风 → 写 /tmp/acnexus_typhoon.json
- 定时任务：每天指定时间触发开关机/自动调温
- 命令队列：轮询 /tmp/acnexus_cmd.json，毫秒级响应前端发指令
"""
import sys, os, json, time
sys.path.insert(0, '/usr/lib/acnexus')

from acnexus_core import init
init()

from acnexus_core.config import load_config, save_config
from acnexus_core.scheduler import re_register

# ── 设备缓存：{mac: broadlink_device} ──
_cached_devices = {}

CMD_FILE = "/tmp/acnexus_cmd.json"
RESULT_FILE = "/tmp/acnexus_result.json"

def _get_broadlink_device(mac, host):
    """获取已认证的博联设备（缓存优先）"""
    if mac in _cached_devices:
        return _cached_devices[mac]

    # 首次认证
    import broadlink
    d = broadlink.hello(host)
    d.auth()
    _cached_devices[mac] = d
    return d

def _process_cmd():
    """处理一条命令，返回结果 dict"""
    try:
        with open(CMD_FILE) as f:
            cmd = json.load(f)
    except Exception:
        return None

    mac = cmd.get("mac", "")
    if not mac:
        return None

    # 每次命令都从文件重读配置（设备可能在扫描后新增）
    from acnexus_core.config import load_config as _reload_cfg
    cfg = _reload_cfg()

    devs = cfg.get("devices", {})
    dev = devs.get("broadlink", {}).get(mac) or {}
    host = dev.get("host", "")
    brand = dev.get("brand", "gree") if dev else "gree"

    try:
        # MIoT 设备走局域网协议
        if mac in devs.get("xiaomi_cloud", {}):
            dev = devs["xiaomi_cloud"][mac]
            from acnexus_core.xiaomi_control import send_miot
            msg = send_miot(dev.get("host", ""), dev.get("token", ""),
                          cmd["power"], cmd["mode"], cmd["temp"], cmd["fan"], mac,
                          spec=dev.get("miot_spec"))
            return {"ok": True, "msg": msg, "mac": mac, "ts": time.time()}

        # Broadlink 设备
        if not host:
            return {"ok": False, "error": "设备无 IP 地址", "mac": mac, "ts": time.time()}

        d = _get_broadlink_device(mac, host)

        from acnexus_core.ac_control import _cfg as ac_cfg
        import acnexus_core.config as _cfg_mod

        # 解析品牌
        brand = _cfg_mod.resolve_brand(brand)
        t = min(max(cmd.get("temp", 26), 16), 30)

        # 生成红外码
        try:
            mod = __import__(f"hvac_ir.{brand}", fromlist=[brand])
            cls_name = brand.capitalize()
            sender = getattr(mod, cls_name)()
            mode_map = {"auto": sender.MODE_AUTO, "cool": sender.MODE_COOL,
                        "dry": sender.MODE_DRY, "fan": sender.MODE_FAN,
                        "heat": sender.MODE_HEAT}
            fan_map = {"auto": sender.FAN_AUTO, "1": sender.FAN_1,
                       "2": sender.FAN_2, "3": sender.FAN_3}
            pwr = sender.POWER_ON if cmd["power"] == "on" else sender.POWER_OFF
            m = mode_map.get(cmd["mode"], sender.MODE_COOL)
            f = fan_map.get(cmd["fan"], sender.FAN_AUTO)
            vsw = getattr(sender, "VDIR_SWING", None)
            hsw = getattr(sender, "HDIR_SWING", None)
            sender.send(pwr, m, f, t, vsw, hsw, False)
        except (ModuleNotFoundError, AttributeError):
            mod = __import__(f"protocols.{brand}", fromlist=[brand])
            cls_map = {"haier": "Haier", "aux_ac": "AUX", "panasonic": "Panasonic"}
            cls_name = cls_map.get(brand, brand.capitalize())
            sender = getattr(mod, cls_name)()
            mode_maps = {
                "haier": {"auto": 0x00, "cool": 0x01, "dry": 0x02, "fan": 0x04, "heat": 0x03},
                "aux_ac": {"auto": 0, "cool": 1, "dry": 2, "fan": 6, "heat": 4},
                "panasonic": {"auto": 0, "cool": 3, "dry": 2, "fan": 6, "heat": 4},
            }
            fan_maps = {
                "haier": {"auto": 0x00, "1": 0x01, "2": 0x02, "3": 0x03},
                "aux_ac": {"auto": 5, "1": 1, "2": 2, "3": 3},
                "panasonic": {"auto": 7, "1": 3, "2": 2, "3": 1},
            }
            mode_map = mode_maps.get(brand, {"auto": 0, "cool": 1, "dry": 2, "fan": 3, "heat": 4})
            fan_map = fan_maps.get(brand, {"auto": 7, "1": 0, "2": 1, "3": 2})
            pwr = mod.POWER_ON if cmd["power"] == "on" else mod.POWER_OFF
            m = mode_map.get(cmd["mode"], mode_map["cool"])
            f = fan_map.get(cmd["fan"], fan_map["auto"])
            sender.send(pwr, m, f, t)

        from broadlink.remote import pulses_to_data
        data = pulses_to_data(sender.get_durations())
        d.send_data(data)

        from datetime import datetime
        MODES = {"制冷": "cool", "制热": "heat", "除湿": "dry", "送风": "fan", "自动": "auto", "关闭": "off"}
        MODE_KEYS = {v: k for k, v in MODES.items()}
        now = datetime.now()
        if cmd["power"] == "on":
            msg = f"[{now:%H:%M}] 手动开机 → {MODE_KEYS.get(cmd['mode'], cmd['mode'])} {t}°C"
        else:
            msg = f"[{now:%H:%M}] 手动关机"

        # 写日志
        from acnexus_core.logger import write_log
        write_log("空调", msg)

        return {"ok": True, "msg": msg, "mac": mac, "ts": time.time()}

    except Exception as e:
        _cached_devices.pop(mac, None)  # 认证可能过期，清除缓存下次重试
        return {"ok": False, "error": str(e), "mac": mac, "ts": time.time()}

# ── 定时刷新 ──
weather_interval = 600
typhoon_interval = 1800
last_weather = 0
last_typhoon = 0

def refresh_weather():
    global last_weather
    try:
        from acnexus_core.weather import fetch_weather
        w = fetch_weather()
        if w:
            tmp = "/tmp/acnexus_weather.json.tmp"
            with open(tmp, "w") as f:
                json.dump({"ts": time.time(), "data": w}, f)
            os.rename(tmp, "/tmp/acnexus_weather.json")
    except Exception:
        pass
    last_weather = time.time()

def refresh_typhoon():
    global last_typhoon
    try:
        from acnexus_core.typhoon import fetch_and_cache
        fetch_and_cache()
    except Exception:
        pass
    last_typhoon = time.time()

refresh_weather()
refresh_typhoon()
re_register()

# ── 主循环 ──
CMD_POLL_WAIT = 0.3  # 300ms 轮询间隔
cfg_reload_at = 0
cfg = load_config()

while True:
    # 命令队列：毫秒级响应
    if os.path.exists(CMD_FILE):
        # 每 30 秒重读一次配置（设备变化时自动感知）
        if time.time() - cfg_reload_at > 30:
            cfg = load_config()
            cfg_reload_at = time.time()

        result = _process_cmd()
        if result:
            try:
                with open(RESULT_FILE, "w") as f:
                    json.dump(result, f)
            except Exception:
                pass
        try:
            os.remove(CMD_FILE)
        except Exception:
            pass
        time.sleep(0.1)
        continue

    # 定期刷新天气/台风
    if time.time() - last_weather > weather_interval:
        refresh_weather()
    if time.time() - last_typhoon > typhoon_interval:
        refresh_typhoon()

    time.sleep(CMD_POLL_WAIT)
