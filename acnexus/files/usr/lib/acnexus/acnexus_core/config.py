"""AC-Nexus-OpenWRT Core — 配置与初始化

多品牌设备结构:
  config["devices"] = {
      "broadlink":     {mac: {host, port, name, brand, ...}},
      "xiaomi_cloud":  {did: {token, model, miot_spec, ...}}
  }
"""

import json
from pathlib import Path

# ── 路径常量 ──
APP_DIR = Path("/root/.ac_controller")
CONFIG_FILE = APP_DIR / "config.json"
LOG_DIR = APP_DIR / "logs"

# ── 运行时全局 ──
LOCATION = {"lat": 39.90, "lon": 116.40, "name": "北京"}
QW_KEY = ""
QW_HOST = ""
AC_BRAND = "gree"

# ── 品牌映射 ──
AC_BRANDS = {
    "格力": "gree", "美的": "midea", "海尔": "haier", "华凌": "midea",
    "奥克斯": "aux_ac", "海信": "hisense", "大金": "daikin", "三菱": "mitsubishi",
    "小米": "midea", "松下": "panasonic",
    "日立": "hitachi", "富士通": "fujitsu", "巴鲁": "ballu",
    "开利": "carriermca", "现代": "hyundai", "Fuego": "fuego",
}


def resolve_brand(raw):
    if not raw:
        return "gree"
    key = AC_BRANDS.get(raw) or AC_BRANDS.get(raw.lower()) or AC_BRANDS.get(raw.capitalize())
    if key:
        return key
    return raw.lower() if raw.isascii() else "gree"


DEFAULT_RULES = [
    (36, 99, 24, "cool"), (33, 35, 25, "cool"), (30, 32, 26, "cool"),
    (25, 29, 27, "cool"), (18, 24, 0, "off"),  (0, 17, 28, "heat"),
]

config = None

# ── 多品牌设备迭代 ──

def _iter_devices(cfg=None):
    """遍历所有设备 → (provider, device_id, device_dict)"""
    if cfg is None:
        cfg = config
    devs = cfg.get("devices", {})
    for provider, provider_devs in devs.items():
        if not isinstance(provider_devs, dict):
            continue
        for device_id, dev in provider_devs.items():
            yield provider, device_id, dev


def _find_in_devices(device_id, cfg=None):
    """跨所有品牌查找设备 → (provider, device_dict)，找不到返回 (None, {})"""
    for provider, did, dev in _iter_devices(cfg):
        if did == device_id:
            return provider, dev
    return None, {}

# ── 配置加载/保存 ──

def load_config():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {
        "current_device_mac": "",
        "current_brand_type": "broadlink",
        "devices": {"broadlink": {}, "xiaomi_cloud": {}},
        "typhoon_ac_off": True, "typhoon_provider": "nmc",
        "api_key": "", "qw_host": "", "location": dict(LOCATION),
        "appearance_mode": "system", "baidu_key": "",
        "weather_provider": "baidu", "weather_provider_set": False,
        "enabled": True,
    }


def save_config(cfg):
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def apply_config():
    global QW_KEY, QW_HOST, LOCATION, AC_BRAND
    QW_KEY = config.get("api_key", "")
    QW_HOST = config.get("qw_host", "")
    if QW_HOST and not QW_HOST.startswith("http"):
        QW_HOST = "https://" + QW_HOST
    LOCATION = config.get("location", {"lat": 39.90, "lon": 116.40, "name": "北京"})
    dev = get_current_device()
    AC_BRAND = resolve_brand(dev.get("brand", "格力"))

# ── 设备操作 ──

def get_current_device():
    """返回当前选中设备的配置字典（可能为空 {}）"""
    mac = config.get("current_device_mac", "")
    provider = config.get("current_brand_type", "broadlink")
    return config.get("devices", {}).get(provider, {}).get(mac, {})


def get_device_list():
    """返回所有设备列表 [(device_id, name, provider), ...]"""
    result = []
    for provider, device_id, dev in _iter_devices():
        result.append((device_id, dev.get("name", device_id[:8]), provider))
    return result


def switch_device(device_id):
    """切换到指定设备"""
    provider, dev = _find_in_devices(device_id)
    if not dev:
        return
    config["current_device_mac"] = device_id
    config["current_brand_type"] = provider
    apply_config()


def add_or_update_device(provider, device_id, info):
    """添加或更新设备。同名自动去重。返回 actual_name"""
    if "devices" not in config:
        config["devices"] = {"broadlink": {}, "xiaomi_cloud": {}}
    config["devices"].setdefault(provider, {})
    provider_devs = config["devices"][provider]

    if device_id in provider_devs:
        # 已有设备：不覆盖用户昵称
        old_name = provider_devs[device_id].get("name", "")
        if old_name:
            info = dict(info)
            info.pop("name", None)
    else:
        # 新设备：去重命名
        raw_name = info.get("name", device_id[:8])
        all_names = {d.get("name", "") for _, _, d in _iter_devices()}
        name = raw_name
        i = 2
        while name in all_names:
            name = f"{raw_name} ({i})"
            i += 1
        info["name"] = name

    provider_devs[device_id] = dict(provider_devs.get(device_id, {}))
    provider_devs[device_id].update(info)

    if not config.get("current_device_mac"):
        config["current_device_mac"] = device_id
        config["current_brand_type"] = provider

    return provider_devs[device_id].get("name", device_id[:8])

# ── 初始化 ──

def init(api_key=None, qw_host=None, location=None, brand=None):
    global config, _cached_temp
    try:
        config = load_config()
    except Exception as e:
        config = {
            "current_device_mac": "", "current_brand_type": "broadlink",
            "devices": {"broadlink": {}, "xiaomi_cloud": {}},
            "typhoon_ac_off": True, "typhoon_provider": "nmc",
            "api_key": "", "qw_host": "", "location": dict(LOCATION),
            "appearance_mode": "system", "baidu_key": "",
            "weather_provider": "baidu", "weather_provider_set": False,
            "enabled": True,
        }
        print(f"[init] load_config 失败, 降级运行: {e}")

    changed = False
    if api_key: config["api_key"] = api_key; changed = True
    if qw_host: config["qw_host"] = qw_host; changed = True
    if location: config["location"] = location; changed = True
    if brand:
        dev = get_current_device()
        if dev:
            dev["brand"] = brand
            changed = True
    if changed:
        save_config(config)

    try:
        apply_config()
    except Exception as e:
        print(f"[init] apply_config 失败: {e}")

    try:
        from acnexus_core.scheduler import start_scheduler, start_data_loops
        start_scheduler()
        start_data_loops()
    except Exception as e:
        print(f"[init] 启动调度失败: {e}")

    try:
        from acnexus_core.weather import fetch_weather
        w = fetch_weather()
        if w and w.get("temp"):
            _cached_temp = float(w["temp"])
    except Exception as e:
        print(f"[init] 启动拉天气失败: {e}")

    try:
        from acnexus_core.typhoon import fetch_and_cache
        fetch_and_cache()
    except Exception as e:
        print(f"[init] 启动拉台风失败: {e}")


_cached_temp = None
_online_macs = set()
