"""AC-Nexus-OpenWRT — 小米 IR 遥控器 MIoT 局域网控制

通过原生 socket + token 加密实现 MIoT set_properties 指令。
添加设备时自动拉取 miot-spec siid/piid 映射并写入 config.json。
"""

import socket
import json
import hashlib
import time
import gzip
import ssl
import urllib.request

# ── 纯 Python ARC4（零依赖，替代 pycryptodome）──
class _RC4:
    def __init__(self, key: bytes):
        self._S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + self._S[i] + key[i % len(key)]) & 0xFF
            self._S[i], self._S[j] = self._S[j], self._S[i]
        self._i = self._j = 0

    def encrypt(self, data: bytes) -> bytes:
        i, j = self._i, self._j
        S = self._S
        result = bytearray(len(data))
        for k in range(len(data)):
            i = (i + 1) & 0xFF
            j = (j + S[i]) & 0xFF
            S[i], S[j] = S[j], S[i]
            result[k] = data[k] ^ S[(S[i] + S[j]) & 0xFF]
        self._i, self._j = i, j
        return bytes(result)

# ── 硬编码兜底映射（大多数 IR 遥控器通用）──
_DEFAULT_SPEC = {
    "power": {"siid": 2, "piid": 1},
    "mode":  {"siid": 2, "piid": 2},
    "temp":  {"siid": 2, "piid": 4},
    "fan":   {"siid": 3, "piid": 1},
}

_MODES = {"cool": 0, "dry": 3, "fan": 2, "auto": 1, "heat": 1}
_FANS  = {"auto": 0, "low": 1, "medium": 2, "high": 3}

MIOT_PORT = 54321
_INDEX_PATH = "/usr/lib/acnexus/protocols/miot_ir_remote_index.txt.gz"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _load_index():
    """加载内置 IR 遥控器型号 → type URN 索引"""
    if not __import__("os").path.exists(_INDEX_PATH):
        return {}
    with gzip.open(_INDEX_PATH, "rt", encoding="utf-8") as f:
        index = {}
        for line in f:
            line = line.strip()
            if "|" in line:
                model, urn = line.split("|", 1)
                index[model] = urn
        return index


def fetch_spec_for_model(model):
    """根据遥控器 model 从 miot-spec 拉取 siid/piid 映射。
    先查本地索引 → 有则下载该型号的 spec JSON → 解析返回。
    返回 dict: {"power": {"siid":2,"piid":1}, "mode":{...}, ...} 失败返回 None。
    """
    index = _load_index()
    urn = index.get(model)
    if not urn:
        return None  # 索引中无此型号，用硬编码兜底

    try:
        url = f"https://miot-spec.org/miot-spec-v2/instance?type={urllib.parse.quote(urn)}"
        req = urllib.request.Request(url, headers={"User-Agent": "AC-Nexus-OpenWRT/3.2"})
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx)
        spec = json.loads(resp.read())

        result = {}
        # remote-control 类型的 service 结构:
        # IR 遥控器通常只有一个 service，包含多个 property
        for svc in spec.get("services", []):
            siid = svc.get("iid", 0)
            svc_type = (svc.get("type") or "").lower()
            svc_desc = (svc.get("description") or "").lower()

            for prop in svc.get("properties", []):
                piid = prop.get("iid", 0)
                desc = (prop.get("description") or "").lower()
                ptype = (prop.get("type") or "").lower()

                # IR 遥控器通过描述字段匹配（remote-control 无标准属性名）
                if "switch" in desc or "power" in desc or ("on" in desc and "off" in desc):
                    result["power"] = {"siid": siid, "piid": piid}
                elif "mode" in desc and "sleep" not in desc and "temperature" not in desc:
                    result["mode"] = {"siid": siid, "piid": piid}
                elif "temperature" in desc or "temp" in desc or "setpoint" in desc:
                    result["temp"] = {"siid": siid, "piid": piid}
                elif "fan" in desc or "wind" in desc or "speed" in desc or "airflow" in desc:
                    result["fan"] = {"siid": siid, "piid": piid}

        # 检查完整性：缺任何一个键则回退硬编码
        if {"power", "mode", "temp", "fan"}.issubset(result.keys()):
            return result
        return None  # 部分匹配，降级用硬编码
    except Exception:
        return None


def _miio_encrypt(token, device_id, timestamp, payload):
    key_bytes = hashlib.md5(token.encode()).digest()
    key = hashlib.md5(key_bytes + device_id.encode() + str(timestamp).encode()).digest()
    cipher = _RC4(key)
    cipher.encrypt(bytes(1024))
    return cipher.encrypt(payload.encode("utf-8"))


def _send_miot_raw(host, token, device_id, siid, piid, value):
    ts = int(time.time())
    cmd = json.dumps({
        "id": 1, "method": "set_properties",
        "params": [{"did": device_id, "siid": siid, "piid": piid, "value": value}]
    })
    encrypted = _miio_encrypt(token, device_id, ts, cmd)
    header = bytes([0x21, 0x31])
    header += (len(encrypted) + 32).to_bytes(2, "big")
    header += bytes(8)
    header += device_id.encode().ljust(16, b"\x00")[:16]
    header += int(ts).to_bytes(4, "big")
    header += token.encode().ljust(16, b"\x00")[:16]
    data = header + encrypted
    hp = host.split(":")
    addr = (hp[0], int(hp[1]) if len(hp) > 1 else MIOT_PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    s.sendto(data, addr)
    s.close()


def send_miot(host, token, power, mode, temp, fan, device_id=None, spec=None):
    """发送空调指令到小米 IR 遥控器。spec 为 fetch_spec_for_model 返回值。"""
    if not device_id:
        device_id = str(int(time.time() * 1000))[-12:]
    if not token or len(token) < 16:
        return "错误: 需要有效的设备 token"

    sp = spec if spec and isinstance(spec, dict) and "power" in spec else _DEFAULT_SPEC

    cmds = []
    siid, piid = sp["power"]["siid"], sp["power"]["piid"]
    cmds.append((siid, piid, power == "on"))
    if power == "on":
        siid, piid = sp["mode"]["siid"], sp["mode"]["piid"]
        cmds.append((siid, piid, _MODES.get(mode, 0)))
        siid, piid = sp["temp"]["siid"], sp["temp"]["piid"]
        cmds.append((siid, piid, min(max(int(temp), 16), 30)))
        siid, piid = sp["fan"]["siid"], sp["fan"]["piid"]
        cmds.append((siid, piid, _FANS.get(fan, 0)))

    results = []
    for siid, piid, val in cmds:
        try:
            _send_miot_raw(host, token, device_id, siid, piid, val)
            results.append(f"siid={siid},piid={piid} OK")
        except Exception as e:
            results.append(f"siid={siid},piid={piid} FAIL: {e}")

    return "; ".join(results)
