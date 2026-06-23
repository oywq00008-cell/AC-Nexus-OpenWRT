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
import codecs
import http.cookiejar
import os
import random
import time
import ssl
import urllib.request
import urllib.parse

# OpenWRT python3-light 缺少 unicodedata C 扩展 → 无法加载 encodings.idna
# 注册占位编码避免 urllib 处理域名时崩溃
try:
    codecs.lookup("idna")
except LookupError:
    codecs.register(lambda n: codecs.CodecInfo(
        name="idna",
        encode=lambda s, e="ascii": (s.encode("ascii", "ignore"), len(s)),
        decode=lambda s, e="ascii": (s.decode("ascii", "ignore"), len(s)),
    ) if n == "idna" else None)

import acnexus_core.config as _cfg

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
_UA = "AC-Nexus-OpenWRT/3.2"

def _save_login_state():
    """持久化登录轮询状态到文件（跨 API 进程共享）"""
    try:
        with open("/tmp/acnexus_xiaomi_state.json", "w") as f:
            json.dump({
                "lp": _login_poll_url,
                "start": _login_start,
                "timeout": _login_timeout,
            }, f)
    except Exception:
        pass


def _load_login_state():
    """从文件恢复登录轮询状态"""
    global _login_poll_url, _login_start, _login_timeout
    try:
        with open("/tmp/acnexus_xiaomi_state.json") as f:
            s = json.load(f)
            _login_poll_url = s.get("lp")
            _login_start = s.get("start", 0)
            _login_timeout = s.get("timeout", 0)
    except Exception:
        pass
_login_poll_url = None
_login_start = 0
_login_timeout = 0


def _get_opener():
    """获取带 Cookie 持久化的 URL opener——跨进程保持 session"""
    cj = http.cookiejar.LWPCookieJar()
    cookie_file = "/tmp/acnexus_xiaomi_cookies.txt"
    if os.path.exists(cookie_file):
        try:
            cj.load(cookie_file, ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=_ctx))
    opener._cookie_file = cookie_file  # 挂载保存路径
    return opener


def _save_cookies(opener):
    """保存 Cookie 到文件"""
    try:
        for handler in opener.handlers:
            if isinstance(handler, urllib.request.HTTPCookieProcessor):
                handler.cookiejar.save(opener._cookie_file, ignore_discard=True, ignore_expires=True)
    except Exception:
        pass


def _urlopen(url, data=None, headers=None, timeout=15):
    """带 Cookie 持久化的 HTTP 请求——小米 OAuth 需要跨进程保持 session"""
    if hasattr(_urlopen, "_opener"):
        opener = _urlopen._opener
    else:
        opener = _get_opener()
        _urlopen._opener = opener
    h = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    resp = opener.open(req, timeout=timeout)
    _save_cookies(opener)  # 每次请求后立即保存 cookie
    return resp


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
    """返回本地 ARC4 实现（零外部依赖）—— 兼容 Crypto.Cipher.ARC4.new() 接口"""
    return _RC4


def _encrypt_rc4(password_b64, payload):
    r = _get_arc4()(base64.b64decode(password_b64))
    r.encrypt(bytes(1024))
    return base64.b64encode(r.encrypt(payload.encode())).decode()


def _decrypt_rc4(password_b64, payload):
    r = _get_arc4()(base64.b64decode(password_b64))
    r.encrypt(bytes(1024))
    return r.encrypt(base64.b64decode(payload)).decode()


def generate_enc_signature(url, method, signed_nonce, params):
    """小米 API 加密请求签名"""
    sig = [method.upper(), url.split("com")[1].replace("/app/", "/")]
    for k, v in params.items():
        sig.append(f"{k}={v}")
    sig.append(signed_nonce)
    return base64.b64encode(
        hashlib.sha1("&".join(sig).encode("utf-8")).digest()
    ).decode()


# ── OAuth 登录 ──

def xiaomi_login():
    """Step 1: 获取登录 URL + 长轮询 URL，启动后台轮询。用户用米家 App 扫码登录。"""
    global _login_poll_url, _login_start, _login_timeout
    _load_login_state()
    try:
        params = urllib.parse.urlencode({
            "_qrsize": "480", "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false", "sid": "xiaomiio",
            "serviceParam": "", "_locale": "zh_CN",
            "_dc": str(int(time.time() * 1000)),
        })
        r = _urlopen(f"https://account.xiaomi.com/longPolling/loginUrl?{params}")
        data = _to_json(r.read().decode())
        _login_poll_url = data.get("lp")
        _login_timeout = data.get("timeout", 600)
        _login_start = time.time()
        _save_login_state()

        # 启动后台轮询进程
        import subprocess
        with open("/tmp/acnexus_poller.log", "w") as log:
            subprocess.Popen(
                ["/usr/bin/python3", "/usr/lib/acnexus/xiaomi_poller.py"],
                stdout=log, stderr=log,
            )

        return {"login_url": data.get("loginUrl", ""), "timeout": _login_timeout}
    except Exception as e:
        return {"error": str(e)}


def xiaomi_poll():
    """Step 2: 检查后台轮询是否已完成。后台进程写 token 到 config.json"""
    _load_login_state()
    # 确保 config 已加载
    if _cfg.config is None:
        from acnexus_core.config import load_config
        _cfg.config = load_config()
    ssecurity = _cfg.config.get("xiaomi_ssecurity") if _cfg.config else None
    serviceToken = _cfg.config.get("xiaomi_serviceToken") if _cfg.config else None
    if ssecurity and serviceToken:
        userId = _cfg.config.get("xiaomi_userId", "")
        return {"status": "ok", "userId": str(userId)}
    # 检查是否超时
    if _login_poll_url and time.time() - _login_start > _login_timeout + 10:
        return {"status": "timeout", "error": "登录超时，请重新扫码"}
    if not _login_poll_url:
        return {"status": "error", "error": "未初始化登录，请先点击前往登录"}
    return {"status": "waiting"}


# ── 设备列表 ──

def xiaomi_fetch_devices():
    """Step 3: 用已保存的凭证拉取设备列表 → [{did, name, model, token, localip}, ...]"""
    from acnexus_core.config import load_config
    if _cfg.config is None:
        _cfg.config = load_config()
    ssecurity = _cfg.config.get("xiaomi_ssecurity") if _cfg.config else None
    serviceToken = _cfg.config.get("xiaomi_serviceToken") if _cfg.config else None
    userId = _cfg.config.get("xiaomi_userId") if _cfg.config else ""
    if not ssecurity or not serviceToken:
        return {"error": "未登录，请先扫码"}

    try:
        # 直接调用加密 API（不需要先调 pass/serviceLogin）
        api_base = "https://api.io.mi.com/app"

        nonce = _generate_nonce(int(time.time() * 1000))
        signed = _signed_nonce(ssecurity, nonce)

        # 拉取家庭列表
        homes = _call_encrypted_api(api_base + "/v2/homeroom/gethome", {
            "fg": True, "fetch_share": True, "fetch_share_dev": True,
            "limit": 300, "app_ver": 7,
        }, ssecurity, nonce, signed, userId, serviceToken)
        home_list = homes.get("result", {}).get("homelist", [])
        if not home_list:
            home_list = [item for p in homes.get("result", {}).get("partition", [])
                         for item in p.get("homelist", [])]

        # 拉每个家庭的设备
        devices = []
        seen = set()
        for home in home_list:
            home_id = home.get("id") or home.get("home_id")
            if not home_id:
                continue
            devs = _call_encrypted_api(api_base + "/v2/home/home_device_list", {
                "home_owner": userId, "home_id": home_id,
                "limit": 200, "get_split_device": True, "support_smart_home": True,
            }, ssecurity, nonce, signed, userId, serviceToken)
            dl = devs.get("result", {}).get("device_info") or devs.get("result", {}).get("list") or []
            for dev in dl:
                did = str(dev.get("did", ""))
                if not did or did in seen:
                    continue
                seen.add(did)
                devices.append({
                    "did": did,
                    "name": dev.get("name", ""),
                    "model": dev.get("model", ""),
                    "token": dev.get("token", ""),
                    "localip": dev.get("localip", ""),
                })
        return {"devices": devices}
    except Exception as e:
        return {"error": str(e)}


def _call_encrypted_api(url, data_dict, ssecurity, nonce, signed_nonce, userId, serviceToken):
    """RC4 加密请求小米 API"""
    params = {"data": json.dumps(data_dict)}
    sign = generate_enc_signature(url, "POST", signed_nonce, params)
    params["rc4_hash__"] = sign
    for k, v in list(params.items()):
        params[k] = _encrypt_rc4(signed_nonce, v)
    fields = {
        **params,
        "signature": generate_enc_signature(url, "POST", signed_nonce, params),
        "ssecurity": ssecurity,
        "_nonce": nonce,
    }
    # 收集所有 session cookies
    all_cookies = ""
    try:
        for handler in _urlopen._opener.handlers:
            if isinstance(handler, urllib.request.HTTPCookieProcessor):
                for c in handler.cookiejar:
                    all_cookies += f"{c.name}={c.value}; "
                break
    except Exception:
        pass
    cookie_str = (
        f"{all_cookies}"
        f"userId={userId}; yetAnotherServiceToken={serviceToken}; "
        f"serviceToken={serviceToken}; locale=zh_CN; "
        f"timezone=GMT+08:00; is_daylight=0; dst_offset=0; channel=MI_APP_STORE"
    )
    h = {
        "User-Agent": _agent(),
        "Content-Type": "application/x-www-form-urlencoded",
        "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
        "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        "Accept-Encoding": "identity",
        "Cookie": cookie_str,
    }
    encoded = urllib.parse.urlencode(fields)
    req = urllib.request.Request(url, data=encoded.encode(), headers=h)
    raw_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx))
    resp = raw_opener.open(req, timeout=20)
    dec = _decrypt_rc4(_signed_nonce(ssecurity, fields["_nonce"]), resp.read().decode())
    return json.loads(dec)


def xiaomi_logout():
    """清除登录凭证"""
    for k in ("xiaomi_ssecurity", "xiaomi_serviceToken", "xiaomi_userId"):
        _cfg.config.pop(k, None)
    from acnexus_core.config import save_config
    save_config(_cfg.config)
    return {"ok": True}
