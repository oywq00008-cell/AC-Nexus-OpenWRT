"""AC-Nexus-OpenWRT — 小米云 OAuth 扫码登录 + 设备列表

纯 urllib 实现，零额外依赖。核心流程:
  1. xiaomi_login() → 返回 login_url，前端生成 QR 码
  2. xiaomi_poll()  → 轮询检测登录状态
  3. xiaomi_fetch_devices() → 返回米家设备列表
"""

import json
import hashlib
import hmac
import base64
import os
import random
import time
import ssl
import urllib.request
import urllib.parse

import acnexus_core.config as _cfg

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
_UA = "AC-Nexus-OpenWRT/3.2"

# ── OAuth 状态 ──
_login_poll_url = None
_login_start = 0
_login_timeout = 0


def _urlopen(url, data=None, headers=None, timeout=15):
    h = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=_ctx)


def _agent():
    agent_id = "".join(chr(random.randint(65, 69)) for _ in range(13))
    random_text = "".join(chr(random.randint(97, 122)) for _ in range(18))
    return f"{random_text}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"


def _to_json(text):
    return json.loads(text.replace("&&&START&&&", ""))


# ── 加密工具 ──

def _signed_nonce(ssecurity, nonce):
    h = hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce))
    return base64.b64encode(h.digest()).decode()


def _generate_nonce(millis):
    nonce_bytes = os.urandom(8) + (int(millis / 60000)).to_bytes(4, byteorder='big')
    return base64.b64encode(nonce_bytes).decode()


# ── 纯 Python ARC4（零依赖，替代 pycryptodome）──
def _arc4_encrypt(key: bytes, data: bytes) -> bytes:
    """RC4 流密码加密/解密（对称）"""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    i = j = 0
    result = bytearray(len(data))
    for k in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        result[k] = data[k] ^ S[(S[i] + S[j]) & 0xFF]
    return bytes(result)


class _RC4:
    """pycryptodome ARC4 兼容接口"""
    def __init__(self, key: bytes):
        self._key = key
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


def _get_arc4():
    """返回本地 ARC4 实现（零外部依赖）"""
    return _RC4


def _encrypt_rc4(password_b64, payload):
    r = _get_arc4().new(base64.b64decode(password_b64))
    r.encrypt(bytes(1024))
    return base64.b64encode(r.encrypt(payload.encode())).decode()


def _decrypt_rc4(password_b64, payload):
    r = _get_arc4().new(base64.b64decode(password_b64))
    r.encrypt(bytes(1024))
    return r.encrypt(base64.b64decode(payload)).decode()


# ── OAuth 登录 ──

def xiaomi_login():
    """Step 1: 获取登录 URL 和长轮询端点。返回 {login_url, timeout}"""
    global _login_poll_url, _login_start, _login_timeout
    try:
        params = urllib.parse.urlencode({
            "_qrsize": "480", "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false", "sid": "xiaomiio",
            "serviceParam": "", "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000)),
        })
        r = _urlopen(f"https://account.xiaomi.com/longPolling/loginUrl?{params}")
        data = _to_json(r.read().decode())
        _login_poll_url = data.get("lp")
        _login_timeout = data.get("timeout", 600)
        _login_start = time.time()
        return {"login_url": data.get("loginUrl", ""), "timeout": _login_timeout}
    except Exception as e:
        return {"error": str(e)}


def xiaomi_poll():
    """Step 2: 轮询检测扫码结果。返回 {status, ssecurity, serviceToken, userId}"""
    global _login_poll_url, _login_start, _login_timeout
    if not _login_poll_url:
        return {"status": "error", "error": "未初始化登录，请先调用 xiaomi_login"}
    if time.time() - _login_start > _login_timeout + 10:
        return {"status": "timeout", "error": "登录超时"}
    try:
        r = _urlopen(_login_poll_url, headers={"User-Agent": _agent()}, timeout=20)
        if r.status != 200:
            return {"status": "waiting"}
        resp = _to_json(r.read().decode())
        ssecurity = resp.get("ssecurity", "")
        userId = resp.get("userId", "")
        location_url = resp.get("location", "")
        if not ssecurity:
            return {"status": "waiting"}

        # 获取 serviceToken
        r2 = _urlopen(location_url, headers={"User-Agent": _agent()}, timeout=15)
        # 从 response headers 或 body 提取 cookie
        serviceToken = None
        for h in r2.info().get_all("Set-Cookie") or []:
            for part in h.split(";"):
                part = part.strip()
                if part.startswith("serviceToken="):
                    serviceToken = part.split("=", 1)[1]
        if not serviceToken:
            serviceToken = r2.read().decode(errors="replace")[:512]
            return {"status": "error", "error": f"无法获取 serviceToken: {serviceToken[:200]}"}

        # 保存凭证到 config
        _cfg.config["xiaomi_ssecurity"] = ssecurity
        _cfg.config["xiaomi_serviceToken"] = serviceToken
        _cfg.config["xiaomi_userId"] = str(userId)
        from acnexus_core.config import save_config
        save_config(_cfg.config)

        return {"status": "ok", "userId": str(userId)}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "waiting"}
        return {"status": "error", "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "waiting"}


# ── 设备列表 ──

def xiaomi_fetch_devices():
    """Step 3: 用已保存的凭证拉取设备列表 → [{did, name, model, token}, ...]"""
    ssecurity = _cfg.config.get("xiaomi_ssecurity")
    serviceToken = _cfg.config.get("xiaomi_serviceToken")
    userId = _cfg.config.get("xiaomi_userId")
    if not ssecurity or not serviceToken:
        return {"error": "未登录，请先扫码"}

    try:
        # 获取 cookies + 认证
        cookie_str = f"userId={userId}; serviceToken={serviceToken}"
        r = _urlopen("https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true",
                     headers={"Cookie": cookie_str})
        data = _to_json(r.read().decode())

        # 重定向到 API 网关
        location = data.get("location")
        if not location:
            return {"error": "认证失败，请重新登录"}

        # 提取 ssecurity 和 nonce
        import re
        ssecurity_match = re.search(r'ssecurity=([^&]+)', location)
        nonce_match = re.search(r'nonce=([^&]+)', location)
        if not ssecurity_match:
            nonce = _generate_nonce(int(time.time() * 1000))
            ssecurity = data.get("ssecurity", "")
        else:
            ssecurity = ssecurity_match.group(1)
            nonce = nonce_match.group(1) if nonce_match else _generate_nonce(int(time.time() * 1000))

        signed = _signed_nonce(ssecurity, nonce)
        c_user_id = data.get("cUserId", data.get("userId", ""))
        ssecurity_for_cookie = data.get("ssecurity", "")

        # 获取服务令牌
        service_url = location + "&clientSign=" + urllib.parse.quote(signed)
        r2 = _urlopen(service_url, headers={"Cookie": cookie_str})
        service_data = json.loads(r2.read().decode())

        # 拉设备列表
        device_cookie = (
            f"cUserId={c_user_id}; "
            f"ssecurity={ssecurity_for_cookie}; "
            f"serviceToken={serviceToken}"
        )

        millis = int(time.time() * 1000)
        nonce2 = _generate_nonce(millis)
        signed_nonce = _signed_nonce(ssecurity, nonce2)

        device_resp = _urlopen(
            f"https://api.io.mi.com/app/home/device_list",
            headers={"Cookie": device_cookie,
                     "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                     "Accept": "application/json"})

        raw = device_resp.read().decode()
        # 尝试解密
        try:
            decrypted = _decrypt_rc4(signed_nonce, raw)
            devices_raw = json.loads(decrypted)
        except Exception:
            devices_raw = json.loads(raw)

        result = devices_raw.get("result", {})
        device_list = result.get("list", [])

        devices = []
        for d in device_list:
            did = str(d.get("did", ""))
            model = d.get("model", "")
            name = d.get("name", model)
            token = d.get("token", "")
            localip = d.get("localip", "")
            devices.append({"did": did, "model": model, "name": name, "token": token, "localip": localip})

        return {"devices": devices}
    except Exception as e:
        return {"error": str(e)}


def xiaomi_logout():
    """清除登录凭证"""
    for k in ("xiaomi_ssecurity", "xiaomi_serviceToken", "xiaomi_userId"):
        _cfg.config.pop(k, None)
    from acnexus_core.config import save_config
    save_config(_cfg.config)
    return {"ok": True}
