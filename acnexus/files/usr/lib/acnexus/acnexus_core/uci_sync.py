#!/usr/bin/python3
"""CBI 设置页保存后同步 UCI → config.json
由 CBI on_commit 自动调用，保留 xiaomi_cloud 设备不覆盖。
"""
import json, subprocess, os, shlex

CFG_FILE = "/root/.ac_controller/config.json"

def uci_get_global(key, default=""):
    try:
        r = subprocess.run(["uci", "get", f"acnexus.@acnexus[0].{key}"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else default
    except:
        return default

def find_device_sections():
    """从 UCI 找出所有有 MAC 的设备节 → [{mac, name, brand, host, port}, ...]"""
    result = []
    try:
        out = subprocess.run(["uci", "show", "acnexus"], capture_output=True, text=True).stdout
        sections = {}
        for line in out.splitlines():
            if "=" not in line:
                continue
            sec, kv = line.split("=", 1)
            if ".device[" not in sec:
                continue
            sec_name = sec.split(".device[")[0] + ".device[" + sec.split(".device[")[1].split("]")[0] + "]"
            key = sec.split(".")[-1]
            val = kv.strip().strip("'").strip('"')
            sections.setdefault(sec_name, {})
            sections[sec_name][key] = val

        for sec_name, vals in sections.items():
            mac = vals.get("mac", "").strip()
            if mac:
                result.append({
                    "mac": mac,
                    "name": vals.get("name", mac[:8]),
                    "brand": vals.get("brand", "gree"),
                    "host": vals.get("host", ""),
                    "port": int(vals.get("port", "80") or "80"),
                })
    except:
        pass
    return result

# ── 主逻辑 ──
cfg = {}
if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except:
        pass

# 全局设置
cfg["api_key"] = uci_get_global("api_key")
cfg["qw_host"] = uci_get_global("qw_host")
cfg["baidu_key"] = uci_get_global("baidu_key")
cfg["weather_provider"] = uci_get_global("weather_provider", "baidu")
cfg["weather_provider_set"] = True
cfg["enabled"] = uci_get_global("enabled", "1") == "1"
cfg["typhoon_provider"] = uci_get_global("typhoon_provider", "nmc")
cfg["typhoon_ac_off"] = uci_get_global("typhoon_ac_off", "1") == "1"

try:
    cfg["location"] = {
        "lat": float(uci_get_global("location_lat", "39.9")),
        "lon": float(uci_get_global("location_lon", "116.4")),
        "name": uci_get_global("location_name", "Beijing")
    }
except:
    pass

# 初始化 devices 结构
cfg.setdefault("devices", {})
cfg["devices"].setdefault("broadlink", {})
cfg["devices"].setdefault("xiaomi_cloud", {})

# 同步博联设备（只更新 UCI 中存在的，不覆盖 xiaomi_cloud）
for d in find_device_sections():
    mac = d["mac"]
    existing = cfg["devices"]["broadlink"].get(mac, {})
    if not existing.get("name"):
        existing["name"] = d["name"]
    existing.update({"mac": mac, "host": d["host"], "port": d["port"], "brand": d["brand"]})
    cfg["devices"]["broadlink"][mac] = existing

os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
with open(CFG_FILE, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
