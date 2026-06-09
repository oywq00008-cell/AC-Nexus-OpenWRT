"""BroadlinkAC Core — 天气与城市搜索"""

import json
import gzip
import ssl
import urllib.request
import urllib.parse
import broadlinkac_core.config as _cfg


def _urlopen(url, timeout=8):
    """兼容 Windows：绕过自签名证书验证"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "BroadlinkAC/2.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def fetch_weather():
    """获取实况天气（根据 provider 路由，回退策略见下）

    回退策略（用户明确）：
    1. 用户显式选百度（weather_provider_set=True）→ 只用百度，失败返回 None（不强制回落，让用户感知到 key 失效）
    2. 用户未显式选（默认 baidu + provider_set=False）→ 百度失败回落和风
    3. 用户选和风（weather_provider=qweather）→ 直接和风
    4. 双源都失败 → 兜底用 _last_weather 旧缓存（10min 内不至于"完全没数据"）
    5. 拉到新数据立即 _set_last_weather（weather_loop 调用方负责）
    """
    provider = _cfg.config.get("weather_provider", "baidu")
    if provider == "baidu":
        result = _fetch_weather_baidu()
        if result is not None:
            return result
        # 百度失败
        if _cfg.config.get("weather_provider_set", False):
            # 用户显式选百度 → 不强制回落
            return None
        # 未显式选 → 回落和风
        result = _fetch_weather_qweather()
        if result is not None:
            return result
    else:
        # provider == qweather → 直接和风
        result = _fetch_weather_qweather()
        if result is not None:
            return result
    # 兜底：双源都失败 → 用旧缓存（哪怕过期 30min 也比"完全没数据"好）
    return _try_fallback()


def city_lookup(query: str):
    """OpenStreetMap 搜索 → [{name, display, lat, lon}, ...]"""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 8,
        "accept-language": "zh", "countrycodes": "cn"
    })
    try:
        raw = _urlopen(url).read()
        data = json.loads(raw)
        return [{
            "name": r.get("name", ""),
            "display": r.get("display_name", ""),
            "lat": float(r["lat"]), "lon": float(r["lon"]),
        } for r in data]
    except Exception as e:
        print(f"[Nominatim] {e}")
    return []


def fetch_weather_alerts():
    """获取当地天气预警 → (数据列表, 实际数据源)
    未明确指定时降级：百度无预警则回退和风。
    """
    provider = _cfg.config.get("weather_provider", "baidu")
    if provider == "baidu":
        result = _fetch_weather_alerts_baidu()
        if result or _cfg.config.get("weather_provider_set", False):
            return result, "baidu"
        result = _fetch_weather_alerts_qweather()
        return result, "qweather" if result else "baidu"
    result = _fetch_weather_alerts_qweather()
    return result, "qweather" if result else "baidu"


def _fetch_weather_baidu():
    """百度实况 → 标准化字段"""
    key = _cfg.config.get("baidu_key", "")
    if not key:
        print("[百度实况] 无 baidu_key, 跳过 → 回落和风")
        return None
    lat = _cfg.LOCATION["lat"]
    lon = _cfg.LOCATION["lon"]
    url = (f"https://api.map.baidu.com/weather/v1/?"
           f"location={lon},{lat}&coordtype=wgs84&data_type=now&ak={key}")
    try:
        raw = _urlopen(url).read()
        data = json.loads(raw)
        if data.get("status") == 0:
            n = data["result"]["now"]
            return {
                "temp": str(n["temp"]),
                "text": n["text"],
                "humidity": str(n["rh"]),
                "windDir": n["wind_dir"],
                "windScale": n["wind_class"].replace("级", ""),
                "feelsLike": str(n["feels_like"]),
                "obsTime": n.get("uptime", ""),
            }
    except Exception as e:
        print(f"[百度实况] {e}")
    return None


def _fetch_weather_alerts_baidu():
    """百度预警 → [{headline, severity, description, ...}]"""
    key = _cfg.config.get("baidu_key", "")
    if not key:
        return []
    lat = _cfg.LOCATION["lat"]
    lon = _cfg.LOCATION["lon"]
    url = (f"https://api.map.baidu.com/weather/v1/?"
           f"location={lon},{lat}&coordtype=wgs84&data_type=alert&ak={key}")
    try:
        raw = _urlopen(url).read()
        data = json.loads(raw)
        if data.get("status") == 0:
            alerts = []
            for a in data["result"].get("alerts", []):
                sev_map = {"蓝色预警": "minor", "黄色预警": "moderate",
                           "橙色预警": "severe", "红色预警": "extreme"}
                alerts.append({
                    "headline": a.get("title", ""),
                    "severity": sev_map.get(a.get("level", ""), "minor"),
                    "description": a.get("desc", ""),
                    "senderName": a.get("type", "") + "预警",
                    "effectiveTime": "", "expireTime": "",
                })
            return alerts
    except Exception as e:
        print(f"[百度预警] {e}")
    return []


def _fetch_weather_qweather():
    """和风实况 → 原始格式"""
    url = f"{_cfg.QW_HOST}/v7/weather/now?location={_cfg.LOCATION['lon']},{_cfg.LOCATION['lat']}&key={_cfg.QW_KEY}"
    try:
        raw = _urlopen(url).read()
        data = json.loads(gzip.decompress(raw))
        if data["code"] == "200":
            return data["now"]
    except Exception as e:
        print(f"[和风天气] {e}")
    return None


# 缓存最后一次成功的天气（key 失效时回退用）
_last_weather = None


def _set_last_weather(w):
    """暴露给 _weather_loop 用：每次拉到新数据就更新"""
    global _last_weather
    if w:
        _last_weather = w


def _try_fallback():
    """和风也失败时，返回最后一次成功的天气（10min 内能"看到旧值"）"""
    return _last_weather


def _fetch_weather_alerts_qweather():
    """和风预警 → 原始格式"""
    host = _cfg.QW_HOST
    key = _cfg.QW_KEY
    if not host or not key:
        return []
    lat = _cfg.LOCATION["lat"]
    lon = _cfg.LOCATION["lon"]
    url = f"{host}/weatheralert/v1/current/{lat:.2f}/{lon:.2f}?key={key}"
    try:
        raw = _urlopen(url).read()
        data = json.loads(gzip.decompress(raw))
        return data.get("alerts", [])
    except Exception as e:
        print(f"[和风预警] {e}")
    return []
