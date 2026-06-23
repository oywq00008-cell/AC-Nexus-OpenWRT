#!/usr/bin/env python3
"""AC-Nexus-OpenWRT — 小米 OAuth 后台轮询进程
由 xiaomi_login() 通过 nohup 启动，持续轮询 lp URL 直到登录成功或超时。
"""

import sys, os, json, time
sys.path.insert(0, '/usr/lib/acnexus')

# 等待前台进程写完 cookie 文件（避免竞态）
time.sleep(0.5)

import acnexus_core.xiaomi_cloud as xc

# 恢复登录状态（lp URL、超时时间等）—— 通过模块访问避免 import 时的值绑定
xc._load_login_state()

if not xc._login_poll_url:
    print("POLLER_ERROR: no poll URL", file=sys.stderr)
    sys.exit(1)

deadline = xc._login_start + max(xc._login_timeout, 10) + 30
print(f"POLLER_START lp={xc._login_poll_url[:80]} deadline={deadline:.0f}", file=sys.stderr)

while time.time() < deadline:
    try:
        r = xc._urlopen(xc._login_poll_url, headers={"User-Agent": xc._agent()}, timeout=25)
        if r.status == 200:
            resp = xc._to_json(r.read().decode())
            ssecurity = resp.get("ssecurity", "")
            userId = resp.get("userId", "")
            location_url = resp.get("location", "")

            if not ssecurity:
                print("POLLER_RETRY no ssecurity yet", file=sys.stderr)
                time.sleep(3)
                continue

            # 获取 serviceToken（跟随 location 重定向，从 Cookie 提取）
            try:
                r2 = xc._urlopen(location_url, headers={"User-Agent": xc._agent()}, timeout=15)
                serviceToken = None
                for h in r2.info().get_all("Set-Cookie") or []:
                    for part in h.split(";"):
                        part = part.strip()
                        if part.startswith("serviceToken="):
                            serviceToken = part.split("=", 1)[1]
                            break
                    if serviceToken:
                        break

                if not serviceToken:
                    print("POLLER_RETRY no serviceToken in cookies", file=sys.stderr)
                    time.sleep(3)
                    continue

                # 写入 config.json
                import acnexus_core.config as cfg
                from acnexus_core.config import load_config, save_config
                cfg.config = load_config()
                cfg.config["xiaomi_ssecurity"] = ssecurity
                cfg.config["xiaomi_serviceToken"] = serviceToken
                cfg.config["xiaomi_userId"] = str(userId)
                save_config(cfg.config)
                print("POLLER_OK", file=sys.stderr)
                sys.exit(0)

            except Exception as e:
                print(f"POLLER_RETRY location error: {e}", file=sys.stderr)
                time.sleep(3)
                continue

        elif r.status == 404:
            time.sleep(2)
            continue
        else:
            print(f"POLLER_RETRY status={r.status}", file=sys.stderr)
            time.sleep(5)

    except Exception as e:
        err = str(e)[:100]
        if "timed out" in err or "timeout" in err.lower():
            time.sleep(2)
            continue
        print(f"POLLER_RETRY error: {err}", file=sys.stderr)
        time.sleep(5)

print("POLLER_TIMEOUT", file=sys.stderr)
