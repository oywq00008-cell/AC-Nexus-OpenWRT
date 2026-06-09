#!/usr/bin/python3
"""BroadlinkAC CGI — API backend for LuCI dashboard"""
import sys, os, json, urllib.parse, traceback
sys.path.insert(0, '/usr/lib/broadlinkac')

def respond(data):
    print("Content-Type: application/json")
    print("Access-Control-Allow-Origin: *")
    print()
    print(json.dumps(data, ensure_ascii=False, default=str))

def handle_status():
    result = {"online": False, "device_name": "未配置", "state": {},
              "weather": {}, "schedule": {}, "storm_dist": 99999, "storm_name": ""}

    # Load config.json or build from UCI
    cfg_path = os.path.expanduser("~/.ac_controller/config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)

    for mac, dev in cfg.get("devices", {}).items():
        result["device_name"] = dev.get("name", mac[:8])
        break
    if not result["device_name"]:
        result["device_name"] = cfg.get("location", {}).get("name", "未配置")

    # Schedule
    result["schedule"]["on"] = cfg.get("trigger_time", "--")
    result["schedule"]["off"] = cfg.get("off_time", "--")

    # Last AC state from log
    try:
        from broadlinkac_core.logger import get_last_ac_state
        state = get_last_ac_state()
        result["state"] = {"power": state.get("power","off"), "mode": state.get("mode","cool"),
                           "temp": state.get("temp",26), "fan": state.get("fan","auto"),
                           "last_action": state.get("raw","")}
    except:
        pass

    # Weather
    try:
        from broadlinkac_core.weather import fetch_weather
        w = fetch_weather()
        if w:
            result["weather"] = {"temp": w.get("temp","--"), "humidity": w.get("humidity","--")}
    except:
        pass

    # Storm
    try:
        from broadlinkac_core.typhoon import typhoon_threat_distance
        dist, name = typhoon_threat_distance()
        result["storm_dist"] = dist
        result["storm_name"] = name
    except:
        pass

    # Device online check
    try:
        from broadlinkac_core import _cfg
        macs = list(cfg.get("devices", {}).keys())
        if macs and hasattr(_cfg, "_online_macs") and macs[0] in _cfg._online_macs:
            result["online"] = True
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
        from broadlinkac_core import init, send_ac
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
