#!/usr/bin/python3
"""AC-Nexus-OpenWRT CGI — API backend for LuCI dashboard"""
import sys, os, json, urllib.parse, traceback
sys.path.insert(0, '/usr/lib/acnexus')

def respond(data):
    print("Content-Type: application/json")
    print("Access-Control-Allow-Origin: *")
    print()
    print(json.dumps(data, ensure_ascii=False, default=str))

def handle_status():
    result = {"online": False, "device_name": "未配置", "state": {},
              "weather": {}, "schedule": {}, "storm_dist": 99999, "storm_name": ""}

    # Load config.json
    cfg_path = "/root/.ac_controller/config.json"
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)

    # 多品牌设备迭代取当前设备名
    current_mac = cfg.get("current_device_mac", "")
    current_provider = cfg.get("current_brand_type", "broadlink")
    devs = cfg.get("devices", {})
    if current_mac:
        current_dev = devs.get(current_provider, {}).get(current_mac, {})
        result["device_name"] = current_dev.get("name", current_mac[:8])
    else:
        # 无当前设备：取第一个
        for prov, prov_devs in devs.items():
            if isinstance(prov_devs, dict) and prov_devs:
                first_did = next(iter(prov_devs))
                result["device_name"] = prov_devs[first_did].get("name", first_did[:8])
                break
    if not result["device_name"]:
        result["device_name"] = cfg.get("location", {}).get("name", "未配置")

    # Schedule（从模板读取，不再使用已废弃的 trigger_time）
    result["schedule"]["on"] = "--"
    result["schedule"]["off"] = "--"
    tmpl_name = current_dev.get("active_template", "") if current_dev else ""
    if tmpl_name:
        tmpl = (cfg.get("schedule_templates") or {}).get(tmpl_name, {})
        slots = (tmpl.get("groups", [{}])[0]).get("slots", [])
        if slots:
            result["schedule"]["on"] = slots[0].get("on", "--")
            result["schedule"]["off"] = slots[0].get("off", "--")

    # Last AC state from log
    try:
        from acnexus_core.logger import get_last_ac_state
        state = get_last_ac_state()
        result["state"] = {"power": state.get("power","off"), "mode": state.get("mode","cool"),
                           "temp": state.get("temp",26), "fan": state.get("fan","auto"),
                           "last_action": state.get("raw","")}
    except:
        pass

    # Weather
    try:
        from acnexus_core.weather import fetch_weather
        w = fetch_weather()
        if w:
            result["weather"] = {"temp": w.get("temp","--"), "humidity": w.get("humidity","--")}
    except:
        pass

    # Storm
    try:
        from acnexus_core.typhoon import typhoon_threat_distance
        dist, name = typhoon_threat_distance()
        result["storm_dist"] = dist
        result["storm_name"] = name
    except:
        pass

    # Device online check (多品牌遍历)
    try:
        import acnexus_core.config as _cfg_mod
        for prov, prov_devs in devs.items():
            if not isinstance(prov_devs, dict):
                continue
            for did, dev in prov_devs.items():
                if prov == "broadlink" and hasattr(_cfg_mod, "_online_macs"):
                    if did in _cfg_mod._online_macs:
                        result["online"] = True
                        break
                elif prov == "xiaomi_cloud":
                    result["online"] = True
                    break
        if not result["online"] and not cfg.get("devices"):
            result["online"] = True  # 无设备不算离线
    except:
        pass

    respond(result)

def handle_send(params):
    parts = params.split()
    if len(parts) < 4:
        respond({"ok": False, "error": "参数不足"})
        return
    power, mode, temp, fan = parts[0], parts[1], int(parts[2]), parts[3]
    try:
        from acnexus_core import init, send_ac
        init()
        r = send_ac(power, mode, temp, fan)
        respond({"ok": True, "name": r})
    except Exception as e:
        respond({"ok": False, "error": str(e)})

# ── Main ──
try:
    qs = os.environ.get("QUERY_STRING", "")
    params = urllib.parse.parse_qs(qs)
    cmd = params.get("cmd", [""])[0].strip()

    if cmd == "status":
        handle_status()
    elif cmd.startswith("send "):
        handle_send(cmd[5:])
    else:
        respond({"ok": False, "error": "未知命令"})
except Exception as e:
    respond({"ok": False, "error": str(e), "trace": traceback.format_exc()})
