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
from pyaes.aes import AESModeOfOperationCBC

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
    "power": {"siid": 3, "piid": 1},
    "mode":  {"siid": 3, "piid": 2},
    "temp":  {"siid": 3, "piid": 4},
    "fan":   {"siid": 4, "piid": 2},
}

_MODES = {"cool": 0, "dry": 4, "fan": 3, "auto": 2}
_FANS  = {"auto": 0, "low": 1, "medium": 2, "high": 3, "1": 1, "2": 2, "3": 3}

MIOT_PORT = 54321
_INDEX_PATH = "/usr/lib/acnexus/protocols/miot_ir_remote_index.txt.gz"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


# ── 在线索引缓存（桌面版同等逻辑：full instances list，7 天缓存）──
_INSTANCES_CACHE = "/tmp/acnexus_miot_instances.txt"
_INSTANCES_TTL  = 7 * 86400  # 7 天


def _load_online_index():
    """从 miot-spec.org 下载全量实例列表并缓存到 /tmp。失败返回 {}。
    
    与桌面版 fetch_miot_spec() 完全对齐：
    1. 检查本地缓存（< 7 天则复用）
    2. 缓存过期则下载 https://miot-spec.org/miot-spec-v2/instances?status=all
    3. 清洗为 model|type 行式缓存并写入文件
    """
    import os as _os
    try:
        instances = None
        if _os.path.exists(_INSTANCES_CACHE):
            age = time.time() - _os.path.getmtime(_INSTANCES_CACHE)
            if age < _INSTANCES_TTL:
                with open(_INSTANCES_CACHE, encoding="utf-8") as f:
                    instances = f.read()

        if instances is None:
            url = "https://miot-spec.org/miot-spec-v2/instances?status=all"
            req = urllib.request.Request(url, headers={"User-Agent": "AC-Nexus-OpenWRT/3.2"})
            resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx)
            raw = json.loads(resp.read()).get("instances", [])
            lines = []
            instances_dict = {}
            for i in raw:
                if i.get("model") and i.get("type"):
                    lines.append(f"{i['model']}|{i['type']}")
                    instances_dict[i["model"]] = i["type"]
            # 原子写入
            tmp = _INSTANCES_CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            _os.rename(tmp, _INSTANCES_CACHE)
            return instances_dict

        # 解析行式缓存
        parsed = {}
        for line in instances.splitlines():
            line = line.strip()
            if "|" in line:
                m, t = line.split("|", 1)
                parsed[m] = t
        return parsed
    except Exception:
        return {}


def fetch_spec_for_model(model):
    """根据遥控器 model 从 miot-spec 拉取 siid/piid 映射。

    查找顺序（与桌面版对齐）：
    1. 本地内置索引（miot_ir_remote_index.txt.gz，含常见 IR 遥控器）
    2. 在线全量索引（miot-spec.org/instances?status=all，缓存 7 天，覆盖全部型号）
    3. 都找不到则返回 None，走 _DEFAULT_SPEC 兜底

    返回 dict: {"power": {"siid":2,"piid":1}, "mode":{...}, ...} 失败返回 None。
    """
    # 第一步：本地内置索引
    urn = None
    if __import__("os").path.exists(_INDEX_PATH):
        with gzip.open(_INDEX_PATH, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    m, u = line.split("|", 1)
                    if m == model:
                        urn = u
                        break

    # 第二步：在线全量索引（桌面版同等逻辑）
    if not urn:
        instances = _load_online_index()
        urn = instances.get(model)
        if not urn:
            return None  # 在线也找不到，走硬编码兜底

    # 第三步：用 urn 拉取该型号的 spec JSON
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


def _miio_encrypt(token_hex, device_id_int, timestamp, payload_bytes):
    """python-miio 兼容加密：AES-128-CBC, key=md5(token), iv=md5(key+token)"""
    token_bytes = bytes.fromhex(token_hex) if len(token_hex) == 32 else token_hex.encode()[:16]
    key = hashlib.md5(token_bytes).digest()
    iv = hashlib.md5(key + token_bytes).digest()
    # PKCS7 padding
    pad = 16 - (len(payload_bytes) % 16)
    plaintext = payload_bytes + bytes([pad]) * pad
    # pyaes AES-128-CBC
    aes = AESModeOfOperationCBC(key, iv=iv)
    result = b''
    for i in range(0, len(plaintext), 16):
        result += aes.encrypt(plaintext[i:i+16])
    return result


def _miio_header_checksum(token_hex, header_bytes, encrypted_data):
    """python-miio 兼容 header checksum: md5(header[0:16] + token + encrypted_data)"""
    token_bytes = bytes.fromhex(token_hex) if len(token_hex) == 32 else token_hex.encode()[:16]
    return hashlib.md5(header_bytes[:16] + token_bytes + encrypted_data).digest()


def _discover_device(host):
    """发送 python-miio 兼容 hello 包，获取设备的真实 numeric device_id。
    返回 (device_id_int, device_timestamp_int) 或 (0, 0)"""
    hello = bytes.fromhex("21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    for _ in range(3):
        try:
            s.sendto(hello, (host, MIOT_PORT))
        except Exception:
            pass
    try:
        resp, _ = s.recvfrom(1024)
        s.close()
        import struct
        device_id = struct.unpack(">I", resp[8:12])[0]
        device_ts = struct.unpack(">I", resp[12:16])[0]
        return device_id, device_ts
    except Exception:
        s.close()
        return 0, 0


def _send_miot_batch(host, token, device_id_str, params, device_id_int=0, device_ts=0):
    """桌面版等效：一次 set_properties 携带全部参数（power/mode/temp/fan）"""
    cmd = json.dumps({
        "id": 1, "method": "set_properties",
        "params": params
    })
    payload_bytes = cmd.encode("utf-8")

    # Handshake
    if not device_id_int:
        device_id_int, device_ts = _discover_device(host)
    if not device_id_int:
        raise Exception("设备无响应（hello 失败）")

    ts = device_ts + 1
    encrypted = _miio_encrypt(token, device_id_int, ts, payload_bytes)
    header16 = bytes([0x21, 0x31])
    header16 += (len(encrypted) + 32).to_bytes(2, "big")
    header16 += (0).to_bytes(4, "big")
    header16 += device_id_int.to_bytes(4, "big")
    header16 += ts.to_bytes(4, "big")
    checksum = _miio_header_checksum(token, header16, encrypted)
    data = header16 + checksum + encrypted
    addr = (host, MIOT_PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    s.sendto(data, addr)
    try:
        s.recvfrom(2048)
    except socket.timeout:
        pass
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
    cmds.append((siid, piid, 1 if power == "on" else 0))
    if power == "on":
        siid, piid = sp["mode"]["siid"], sp["mode"]["piid"]
        cmds.append((siid, piid, _MODES.get(mode, 0)))
        siid, piid = sp["temp"]["siid"], sp["temp"]["piid"]
        cmds.append((siid, piid, min(max(int(temp), 16), 30)))
        siid, piid = sp["fan"]["siid"], sp["fan"]["piid"]
        cmds.append((siid, piid, _FANS.get(fan, 0)))

    # 一次性 hello 获取 device_id
    did_int, dev_ts = _discover_device(host)
    if not did_int:
        return "错误: 设备无响应"

    # 构建一条 set_properties 携带全部参数（桌面版等效）
    params = [{"did": device_id, "siid": s, "piid": p, "value": v} for s, p, v in cmds]
    try:
        _send_miot_batch(host, token, device_id, params, did_int, dev_ts)
        return "; ".join(f"siid={s},piid={p} OK" for s, p, _ in cmds)
    except Exception as e:
        return f"错误: {e}"
