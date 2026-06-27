"""AC-Nexus-OpenWRT Core — 天气与城市搜索"""

import json
import gzip
import ssl
import sys
import urllib.request
import urllib.parse
import acnexus_core.config as _cfg

# OpenWRT python3-light 缺少 unicodedata，注册 idna 占位编码
import codecs
def _idna_encode(s): return (s.encode("ascii", "ignore"), len(s))
def _idna_decode(s): return (s.decode("ascii", "ignore"), len(s))
try:
    codecs.lookup("idna")
except LookupError:
    codecs.register(lambda n: codecs.CodecInfo(_idna_encode, _idna_decode, name="idna") if n == "idna" else None)


def _urlopen(url, timeout=8):
    """兼容透明代理 DNS 劫持：检测 198.18.x.x 假 IP 后走 DoH 解析"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    host = urllib.parse.urlparse(url).hostname
    try:
        import socket
        real_ip = socket.getaddrinfo(host, 443, socket.AF_INET)[0][4][0]
        if real_ip.startswith("198.18."):
            raise socket.gaierror("DNS hijacked")
    except Exception:
        import subprocess
        try:
            doh_url = f"https://dns.google/resolve?name={host}&type=A"
            raw = subprocess.check_output(
                ["wget", "-qO-", "--no-check-certificate", "--secure-protocol=TLSv1_2",
                 "--timeout=5", doh_url], stderr=subprocess.DEVNULL)
            resp = json.loads(raw)
            real_ip = resp["Answer"][0]["data"]
            url = url.replace(f"://{host}", f"://{real_ip}", 1)
            req = urllib.request.Request(url, headers={"User-Agent": "AC-Nexus-OpenWRT/2.0", "Host": host})
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": "AC-Nexus-OpenWRT/2.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def fetch_weather():
    """获取实况天气（根据 provider 路由，回退策略见下）

    回退策略（用户明确）：
    1. 用户显式选百度（weather_provider_set=True）→ 只用百度，失败返回 None（不强制回落，让用户感知到 key 失效）
    2. 用户未显式选（默认 baidu + provider_set=False）→ 百度失败回落和风
    3. 用户选和风（weather_provider=qweather）→ 直接和风
    4. 双源都失败 → 兜底用 _last_weather 旧缓存（10min 内不至于"完全没数据"）
    5. 拉到新数据立即更新 _last_weather
    """
    global _last_weather
    provider = _cfg.config.get("weather_provider", "baidu")
    if provider == "baidu":
        result = _fetch_weather_baidu()
        if result is not None:
            _last_weather = result
            return result
        # 百度失败
        if _cfg.config.get("weather_provider_set", False):
            # 用户显式选百度 → 不强制回落
            return None
        # 未显式选 → 回落和风
        result = _fetch_weather_qweather()
        if result is not None:
            _last_weather = result
            return result
    else:
        # provider == qweather → 直接和风
        result = _fetch_weather_qweather()
        if result is not None:
            _last_weather = result
            return result
    # 兜底：双源都失败 → 用旧缓存（哪怕过期 30min 也比"完全没数据"好）
    has_baidu = bool(_cfg.config.get("baidu_key"))
    has_qweather = bool(_cfg.QW_HOST) and bool(_cfg.QW_KEY)
    if not has_baidu and not has_qweather:
        print("[天气] 未配置 API Key，请前往设置页填入", file=sys.stderr)
    elif _last_weather:
        print("[天气] 获取失败，使用缓存", file=sys.stderr)
    else:
        print("[天气] 获取失败，请检查 API Key 或网络", file=sys.stderr)
    return _try_fallback()


def city_lookup(query: str):
    """OpenStreetMap 搜索 → 桌面版使用，WRT 精简版通过 JS 直连 OSM，此处仅保留占位"""
    return []


def _fetch_weather_baidu():
    """百度实况 → 标准化字段"""
    key = _cfg.config.get("baidu_key", "")
    if not key:
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
        print(f"[百度实况] {e}", file=sys.stderr)
    return None


def _fetch_weather_qweather():
    """和风实况 → 原始格式"""
    if not _cfg.QW_HOST or not _cfg.QW_KEY:
        return None
    url = f"{_cfg.QW_HOST}/v7/weather/now?location={_cfg.LOCATION['lon']},{_cfg.LOCATION['lat']}&key={_cfg.QW_KEY}"
    try:
        raw = _urlopen(url).read()
        data = json.loads(gzip.decompress(raw))
        if data["code"] == "200":
            return data["now"]
    except Exception as e:
        print(f"[和风天气] 请求失败", file=sys.stderr)
    return None


# 缓存最后一次成功的天气（key 失效时回退用）
_last_weather = None


def _try_fallback():
    """和风也失败时，返回最后一次成功的天气（10min 内能"看到旧值"）"""
    return _last_weather
