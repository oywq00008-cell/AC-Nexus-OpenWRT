#!/usr/bin/python3
"""AC-Nexus-OpenWRT API — called by LuCI controller, arg is 'status' or 'send <params>'"""
import sys, os, json
sys.path.insert(0, '/usr/lib/acnexus')

def _iter_config_devices(cfg):
    """遍历多品牌设备 {broadlink: {mac: dev}, xiaomi_cloud: {did: dev}}"""
    devs = cfg.get("devices", {})
    for provider, provider_devs in devs.items():
        if not isinstance(provider_devs, dict):
            continue
        for device_id, dev in provider_devs.items():
            yield provider, device_id, dev

def get_current_device_from_cfg(cfg):
    """从多品牌 devices 中获取当前设备"""
    mac = cfg.get("current_device_mac", "")
    provider = cfg.get("current_brand_type", "broadlink")
    return cfg.get("devices", {}).get(provider, {}).get(mac, {}) if mac else {}

def _find_in_cfg_devices(cfg, device_id):
    """跨品牌查找设备 → (provider, dict) 或 (None, {})"""
    for provider, provider_devs in cfg.get("devices", {}).items():
        if isinstance(provider_devs, dict) and device_id in provider_devs:
            return provider, provider_devs[device_id]
    return None, {}

def cfg_get_mac():
    p = "/root/.ac_controller/config.json"
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f).get("current_device_mac", "")
    return ""

def _uci_set_device(mac, dev):
    """同步设备信息到 UCI"""
    if not mac:
        return  # 空 mac 会让 `mac in line` 误匹配所有设备节
    import subprocess
    uci = subprocess.run(['uci', 'show', 'acnexus'], capture_output=True, text=True).stdout
    sec = None
    for line in uci.splitlines():
        # 精确匹配 "section.mac='<mac>'"，避免短 mac 字符串误命中
        if '.mac=' in line:
            val = line.split('.mac=')[-1].strip().strip("'")
            if val == mac:
                sec = line.split('.mac=')[0]
                break
    if not sec:
        subprocess.run(['uci', 'add', 'acnexus', 'device'], capture_output=True)
        sec = 'acnexus.@device[-1]'
    for k in ('name', 'brand', 'host', 'port', 'mac'):
        if k in dev and dev[k]:
            subprocess.run(['uci', 'set', f'{sec}.{k}=' + str(dev[k])], capture_output=True)
    subprocess.run(['uci', 'commit', 'acnexus'], capture_output=True)
    subprocess.run(['rm', '-f', '/tmp/luci-indexcache*'], capture_output=True)

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
result = {}

if cmd == "status" or cmd == "refresh":
    force = (cmd == "refresh")

    # config.json → UCI 反向同步（弹窗存的字段反向写 UCI，让 CBI 页面能显示）
    # 这样用户在弹窗里填的 API key 也能在 CBI 设置页看到
    try:
        import subprocess as _sp
        cfg_path = "/root/.ac_controller/config.json"
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                _cfg_for_uci = json.load(f)
            for _field in ('api_key', 'qw_host', 'baidu_key'):
                _val = _cfg_for_uci.get(_field, '')
                if _val:
                    _r = _sp.run(['uci', 'get', f'acnexus.@acnexus[0].{_field}'],
                                 capture_output=True, text=True)
                    if not _r.stdout.strip():
                        _sp.run(['uci', 'set', f'acnexus.@acnexus[0].{_field}={_val}'])
            _sp.run(['uci', 'commit', 'acnexus'])
    except Exception:
        pass

    # 同步 UCI → config.json（必须在 disabled 短路之前完成，否则 enabled 行被 CBI 删了后无法判断）
    try:
        import subprocess as _sp
        uci = {}
        for line in _sp.run(['uci', 'show', 'acnexus'], capture_output=True, text=True).stdout.splitlines():
            if '=' in line and 'acnexus.@acnexus[0].' in line:
                k, v = line.split('=', 1)
                key = k.split('acnexus.@acnexus[0].')[-1]
                uci[key] = v.strip("'")
        cfg_path = "/root/.ac_controller/config.json"
        if os.path.exists(cfg_path) and uci:
            with open(cfg_path) as f:
                cfg = json.load(f)
            changed = False
            for k, v in uci.items():
                if k in ('weather_provider_set',):
                    cfg[k] = (v == '1')
                    changed = True
                elif k in ('typhoon_ac_off',):
                    cfg[k] = (v == '1')
                    changed = True
                elif k in ('location_lat', 'location_lon'):
                    cfg.setdefault('location', {})
                    cfg['location'][k.replace('location_', '')] = float(v)
                    changed = True
                elif k == 'location_name':
                    cfg.setdefault('location', {})
                    cfg['location']['name'] = v
                    changed = True
                elif k == 'api_key':
                    cfg['api_key'] = v
                    changed = True
                elif k in ('qw_host', 'baidu_key', 'weather_provider', 'typhoon_provider', 'appearance_mode'):
                    cfg[k] = v
                    changed = True
                elif k == 'enabled':
                    cfg['enabled'] = (v == '1')
                    changed = True

            # enabled 特殊处理：CBI 取消勾选时 UCI 会直接删除该行（uhttpd 不写 enabled='0'），
            # 所以这里要主动检查 UCI 中是否完全不存在 enabled 字段 → 视作 False
            if 'enabled' not in uci:
                if cfg.get('enabled', True) is not False:
                    cfg['enabled'] = False
                    changed = True

            # device 节同步...
            for line in _sp.run(['uci', 'show', 'acnexus'], capture_output=True, text=True).stdout.splitlines():
                if '.mac=' in line and line.startswith('acnexus.@device'):
                    sec = line.split('.mac=')[0]
                    uci_mac = line.split('.mac=')[1].strip("'")
                    cfg.setdefault('devices', {})
                    cfg['devices'].setdefault('broadlink', {})
                    d = cfg['devices']['broadlink'].setdefault(uci_mac, {})
                    d['mac'] = uci_mac
                    for f in ('name', 'brand', 'host', 'port'):
                        r = _sp.run(['uci', 'get', f'{sec}.{f}'], capture_output=True, text=True)
                        v = r.stdout.strip()
                        if r.returncode == 0 and v:
                            d[f] = v
                    changed = True

            if changed:
                with open(cfg_path, 'w') as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # 总开关短路：enabled=False 立即返回
    try:
        cfg_path_disabled = "/root/.ac_controller/config.json"
        _cfg_for_disabled = {}
        if os.path.exists(cfg_path_disabled):
            with open(cfg_path_disabled) as f:
                _cfg_for_disabled = json.load(f)
        if not _cfg_for_disabled.get("enabled", True):
            result = {"disabled": True, "online": False,
                      "device_name": "插件已停用", "state": {},
                      "weather": {}, "schedule": {"on": "--", "off": "--"},
                      "storm_dist": 99999, "storm_name": "", "devices": []}
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    except Exception:
        pass

    result = {"online": False, "device_name": "未配置", "state": {},
              "weather": {}, "schedule": {"on": "--", "off": "--"},
              "storm_dist": 99999, "storm_name": "", "devices": []}

    # 加载 config.json
    cfg_path = "/root/.ac_controller/config.json"
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)

    # 初始化 config 全局变量（天气/台风依赖）
    try:
        import acnexus_core.config as _cfg
        _cfg.config = cfg or _cfg.load_config()
        _cfg.apply_config()
    except:
        pass

    # 当前设备和设备列表（多品牌）
    current_mac = cfg.get("current_device_mac", "")
    current_dev = get_current_device_from_cfg(cfg)
    all_devs = list(_iter_config_devices(cfg))
    for provider, device_id, dev in all_devs:
        result["devices"].append({"mac": device_id, "name": dev.get("name", device_id[:8]), "provider": provider})
    
    if not current_dev and all_devs:
        provider, device_id, dev = all_devs[0]
        cfg["current_device_mac"] = device_id
        cfg["current_brand_type"] = provider
        current_mac = device_id
        current_dev = dev
        save_config(cfg)
    
    result["device_name"] = current_dev.get("name", current_mac[:8]) if current_dev else "未配置"

    # 返回当前设备 MAC 供前端设置下拉框
    result["current_device_mac"] = current_mac

    # 在线检测
    if current_dev and current_dev.get("host"):
        try:
            import broadlink
            d = broadlink.hello(current_dev["host"])
            d.auth()
            result["online"] = True
        except:
            pass

    # 定时（从模板读取核心信息，不再使用已废弃的 trigger_time/off_time 字段）
    if current_dev:
        tmpl_name = current_dev.get("active_template", "")
        templates = cfg.get("schedule_templates") or {}
        tmpl = templates.get(tmpl_name, {}) if tmpl_name else {}
        groups = tmpl.get("groups", [])
        result["schedule"]["on"] = "--"
        result["schedule"]["off"] = "--"
        if groups:
            slots = groups[0].get("slots", [])
            if slots and len(slots) >= 1:
                result["schedule"]["on"] = slots[0].get("on", "--")
                result["schedule"]["off"] = slots[0].get("off", "--")
        result["schedule"]["enabled"] = bool(current_dev.get("schedule_enabled"))
        result["schedule"]["on_time"] = result["schedule"]["on"]
        result["schedule"]["off_enabled"] = bool(current_dev.get("off_enabled"))
        result["schedule"]["off_time"] = result["schedule"]["off"]
        result["schedule"]["auto_adjust"] = bool(current_dev.get("auto_adjust", True))
        result["schedule"]["rules"] = current_dev.get("temp_rules") or []

        active_tmpl = current_dev.get("active_template", "")
        result["schedule"]["active_template"] = active_tmpl

    # 模板数据（独立于设备，全局共享）
    templates = cfg.get("schedule_templates") or {}
    result["schedule"]["templates"] = templates
    result["schedule"]["template_name"] = result["schedule"].get("active_template") or ("默认" if templates else "--")

    # 设备详情（品牌等）
    if current_dev:
        result["device_info"] = {
            "brand": current_dev.get("brand", "gree"),
            "brand_display": current_dev.get("brand_display", ""),
            "host": current_dev.get("host", ""),
            "port": current_dev.get("port", 80),
            "mac": current_dev.get("mac", current_mac),
        }

    # 位置
    result["location"] = cfg.get("location", {"lat": 39.9, "lon": 116.4, "name": "未设置"})

    # 最近状态
    try:
        from acnexus_core.logger import get_last_ac_state
        state = get_last_ac_state()
        result["state"] = {"power": state.get("power","off"), "mode": state.get("mode","cool"),
                           "temp": state.get("temp",26), "fan": state.get("fan","auto"),
                           "last_action": state.get("raw","")}
    except:
        pass

    # 天气：force 时直接现场拉，否则缓存优先
    try:
        from acnexus_core import config as _cfg_mod
        _cfg_mod.apply_config()
        if force:
            # 强制拉一次
            from acnexus_core.weather import fetch_weather
            w = fetch_weather()
            if w:
                temp_val = float(w.get("temp", 0)) if w.get("temp") else None
                if temp_val is not None:
                    _cfg_mod._cached_temp = temp_val
                result["weather"] = {"temp": str(w.get("temp", "--")),
                                     "humidity": str(w.get("humidity", w.get("rh", "--"))),
                                     "text": w.get("text", "--")}
            else:
                result["weather"] = {"temp": "--", "humidity": "--", "text": "--"}
        else:
            temp_val = _cfg_mod._cached_temp
            if temp_val is None:
                from acnexus_core.weather import fetch_weather
                w = fetch_weather()
                if w:
                    temp_val = float(w.get("temp", 0)) if w.get("temp") else None
                    if temp_val is not None:
                        _cfg_mod._cached_temp = temp_val
                    result["weather"] = {"temp": str(w.get("temp", "--")),
                                         "humidity": str(w.get("humidity", w.get("rh", "--"))),
                                         "text": w.get("text", "--")}
                else:
                    result["weather"] = {"temp": "--", "humidity": "--", "text": "--"}
            else:
                result["weather"] = {"temp": str(temp_val), "humidity": "--", "text": "--"}
    except Exception as e:
        result["weather"] = {"temp": "--", "humidity": "--", "error": str(e)}

    # 台风：force 时直接现场拉，否则缓存优先
    try:
        from acnexus_core.typhoon import get_cached, typhoon_threat_distance
        from acnexus_core import config as _cfg_mod
        _cfg_mod.apply_config()
        if force:
            from acnexus_core.typhoon import fetch_and_cache, judge_and_shutdown
            from acnexus_core.logger import write_log
            fetch_and_cache()
            # force 时也跑一次判定（judge_and_shutdown 现在内部读日志，不再用 ty_ac_off_sent 标志位）
            judge_and_shutdown(write_log)
        else:
            cache = get_cached()
            if not cache:
                from acnexus_core.typhoon import fetch_and_cache
                fetch_and_cache()
        dist, name = typhoon_threat_distance()
        result["storm_dist"] = dist
        result["storm_name"] = name
    except Exception:
        pass

elif cmd.startswith("switch "):
    mac = cmd[7:].strip()
    try:
        from acnexus_core.config import load_config, save_config
        cfg = load_config()
        provider, dev = _find_in_cfg_devices(cfg, mac)
        if dev:
            cfg["current_device_mac"] = mac
            cfg["current_brand_type"] = provider
            save_config(cfg)
            result = {"ok": True}
        else:
            result = {"ok": False, "error": "设备不存在"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd.startswith("send "):
    parts = cmd[5:].split()
    if len(parts) >= 4:
        power, mode, temp, fan = parts[0], parts[1], int(parts[2]), parts[3]
        try:
            from acnexus_core import init, send_ac
            init()
            r = send_ac(power, mode, temp, fan)
            result = {"ok": True, "name": r}
        except Exception as e:
            result = {"ok": False, "error": str(e)}
    else:
        result = {"ok": False, "error": "参数不足"}

elif cmd.startswith("save_schedule "):
    # base64 JSON: {"mac":"...","templates":{...},"active_template":"...","auto_adjust":bool,"rules":[...]}
    import base64, subprocess as _sp
    try:
        data = json.loads(base64.b64decode(cmd[14:]).decode())
        mac = data.get("mac") or cfg_get_mac()
        from acnexus_core.config import load_config, save_config
        cfg = load_config()
        provider, dev = _find_in_cfg_devices(cfg, mac)
        if not dev:
            dev = cfg.setdefault("devices", {}).setdefault("broadlink", {}).setdefault(mac, {})
        if "templates" in data:
            cfg["schedule_templates"] = data["templates"]
        if "active_template" in data:
            dev["active_template"] = data["active_template"]
        if "schedule_enabled" in data:
            dev["schedule_enabled"] = bool(data["schedule_enabled"])
        if "auto_adjust" in data:
            dev["auto_adjust"] = bool(data["auto_adjust"])
        save_config(cfg)
        _uci_set_device(mac, dev)
        try:
            from acnexus_core.scheduler import re_register
            re_register()
        except Exception:
            pass
        result = {"ok": True}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd.startswith("save_rules "):
    import base64
    try:
        data = json.loads(base64.b64decode(cmd[11:]).decode())
        mac = data.get("mac") or cfg_get_mac()
        from acnexus_core.config import load_config, save_config
        cfg = load_config()
        provider, dev = _find_in_cfg_devices(cfg, mac)
        if not dev:
            dev = cfg.setdefault("devices", {}).setdefault("broadlink", {}).setdefault(mac, {})
        dev["temp_rules"] = data.get("rules", [])
        save_config(cfg)
        _uci_set_device(mac, dev)
        try:
            from acnexus_core.scheduler import re_register
            re_register()
        except Exception:
            pass
        result = {"ok": True}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd.startswith("save_device "):
    import base64, subprocess as _sp
    try:
        data = json.loads(base64.b64decode(cmd[12:]).decode())
        mac = data.get("mac") or cfg_get_mac()
        if not mac:
            result = {"ok": False, "error": "缺少设备 MAC"}
        else:
            from acnexus_core.config import load_config, save_config
            cfg = load_config()
            provider, dev = _find_in_cfg_devices(cfg, mac)
            if not dev:
                dev = cfg.setdefault("devices", {}).setdefault("broadlink", {}).setdefault(mac, {})
            name_error = None
            if "name" in data:
                new_name = data["name"].strip()
                if not new_name:
                    name_error = "名称不能为空"
                else:
                    for _, odid, odev in _iter_config_devices(cfg):
                        if odid != mac and odev.get("name") == new_name:
                            name_error = f"名称「{new_name}」已被其他设备使用"
                            break
                    if not name_error:
                        dev["name"] = new_name
            if name_error:
                result = {"ok": False, "error": name_error}
            else:
                if "brand" in data:
                    dev["brand"] = data["brand"]
                if "brand_display" in data:
                    dev["brand_display"] = data["brand_display"]
                save_config(cfg)
                result = {"ok": True, "name": dev.get("name", ""), "brand": dev.get("brand", "")}
                _uci_set_device(mac, dev)
                result = {"ok": True}
            # 设备字段变化后重注册 schedule（防止新增设备没 job）
            try:
                from acnexus_core.scheduler import re_register
                re_register()
            except Exception:
                pass
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd.startswith("location_save "):
    import base64, subprocess
    try:
        data = json.loads(base64.b64decode(cmd[14:]).decode())
        from acnexus_core.config import load_config, save_config
        cfg = load_config()
        cfg["location"] = {"lat": data["lat"], "lon": data["lon"], "name": data["name"]}
        save_config(cfg)
        # Sync to UCI
        subprocess.run(['uci', 'set', 'acnexus.@acnexus[0].location_lat=' + str(data["lat"])], capture_output=True)
        subprocess.run(['uci', 'set', 'acnexus.@acnexus[0].location_lon=' + str(data["lon"])], capture_output=True)
        subprocess.run(['uci', 'set', 'acnexus.@acnexus[0].location_name=' + data["name"]], capture_output=True)
        subprocess.run(['uci', 'commit', 'acnexus'], capture_output=True)
        subprocess.run(['rm', '-f', '/tmp/luci-indexcache*'], capture_output=True)
        result = {"ok": True}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd == "discover":
    result = {"ok": True, "devices": []}
    try:
        import broadlink, subprocess

        # 1. 自动检测 LAN 接口 IP（优先 br-lan，回退任意 UP 非 lo 接口）
        def get_lan_ip():
            for ifname in ["br-lan", None]:
                args = ["ip", "-4", "-br", "addr", "show"]
                if ifname:
                    args.append(ifname)
                r = subprocess.run(args, capture_output=True, text=True)
                for line in r.stdout.splitlines():
                    if ifname is None and ("lo" in line or "UP" not in line):
                        continue
                    for part in line.split():
                        if "/" in part:
                            return part.split("/")[0]
            raise Exception("找不到 LAN 接口")

        lan_ip = get_lan_ip()

        # 2. 从 LAN 接口广播发现设备
        devices = broadlink.discover(timeout=5, local_ip_address=lan_ip)
        for d in devices:
            mac = d.mac.hex() if hasattr(d.mac, "hex") else str(d.mac)
            result["devices"].append({
                "mac": mac,
                "host": str(d.host[0]),
                "port": d.host[1],
                "model": getattr(d, "model", "?"),
            })

        if not result["devices"]:
            result["ok"] = False
            result["error"] = "未发现博联设备"
        else:
            # 3. 自动写入 config.json
            try:
                from acnexus_core.config import load_config, save_config
                cfg = load_config()
                cfg.setdefault("devices", {})
                cfg["devices"].setdefault("broadlink", {})
                for d in result["devices"]:
                    existing = cfg["devices"]["broadlink"].get(d["mac"], {})
                    model = d.get("model", "") or "博联设备"
                    if not existing.get("name"):
                        existing["name"] = model
                    existing.update({
                        "mac": d["mac"], "host": d["host"],
                        "port": d["port"], "model": model,
                    })
                    cfg["devices"]["broadlink"][d["mac"]] = existing
                if not cfg.get("current_device_mac"):
                    cfg["current_device_mac"] = result["devices"][0]["mac"]
                    cfg["current_brand_type"] = "broadlink"
                save_config(cfg)
                result["saved"] = True

                # 4. 同步到 UCI（供 CBI 设置页读取）
                # 先清理空条目（无 MAC 的设备节）
                uci_show = subprocess.run(['uci', 'show', 'acnexus'], capture_output=True, text=True).stdout
                has_mac = set()
                for line in uci_show.splitlines():
                    if '.mac=' in line:
                        has_mac.add(line.split('.mac=')[0])
                for line in uci_show.splitlines():
                    if '=device' in line and line.startswith("acnexus.@device"):
                        sec = line.split('=')[0]
                        if sec not in has_mac:
                            subprocess.run(['uci', 'delete', sec], capture_output=True)
                subprocess.run(['uci', 'commit', 'acnexus'], capture_output=True)

                # 写入/更新设备
                for d in result["devices"]:
                    uci_show = subprocess.run(['uci', 'show', 'acnexus'], capture_output=True, text=True).stdout
                    section_name = None
                    for line in uci_show.splitlines():
                        if d["mac"] in line and ".mac=" in line:
                            section_name = line.split(".mac=")[0]; break
                    if not section_name:
                        subprocess.run(['uci', 'add', 'acnexus', 'device'], capture_output=True)
                        section_name = 'acnexus.@device[-1]'
                        subprocess.run(['uci', 'set', f'{section_name}.name=' + d.get('model', '博联设备')], capture_output=True)
                    subprocess.run(['uci', 'set', f'{section_name}.mac=' + d['mac']], capture_output=True)
                    subprocess.run(['uci', 'set', f'{section_name}.host=' + d['host']], capture_output=True)
                    subprocess.run(['uci', 'set', f'{section_name}.port=' + str(d.get('port', 80))], capture_output=True)
                subprocess.run(['uci', 'commit', 'acnexus'], capture_output=True)
                subprocess.run(['rm', '-f', '/tmp/luci-indexcache*'], capture_output=True)
                result["uci_synced"] = True
            except Exception:
                result["saved"] = False

            # 设备增删后重新注册 schedule 任务（仅在 init 之后才有 scheduler 线程）
            try:
                from acnexus_core.scheduler import re_register
                re_register()
            except Exception:
                pass

    except ImportError:
        result = {"ok": False, "error": "broadlink 库未安装"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd == "help_doc":
    # 返回使用指南文档内容
    try:
        doc_path = "/usr/share/acnexus/docs/guide.md"
        if os.path.exists(doc_path):
            with open(doc_path, "r", encoding="utf-8") as f:
                result = {"ok": True, "content": f.read()}
        else:
            result = {"ok": False, "error": "文档未找到"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

elif cmd == "log_dates":
    # 列出所有有日志的日期（前端用于日期网格标红/可点）
    try:
        from acnexus_core.logger import get_log_dates
        result = {"ok": True, "dates": get_log_dates()}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

# log_download 已移至 controller.lua 的独立 endpoint（绕开 luci.sys.exec 的 4KB 截断）

elif cmd == "xiaomi_login":
    try:
        from acnexus_core.xiaomi_cloud import xiaomi_login
        result = xiaomi_login()
    except Exception as e:
        result = {"error": str(e)}

elif cmd == "xiaomi_poll":
    try:
        from acnexus_core.xiaomi_cloud import xiaomi_poll
        result = xiaomi_poll()
    except Exception as e:
        result = {"error": str(e)}

elif cmd == "xiaomi_devices":
    try:
        from acnexus_core.xiaomi_cloud import xiaomi_fetch_devices
        r = xiaomi_fetch_devices()
        if "error" in r:
            result = r
        else:
            # 标记已添加的设备
            cfg = load_config()
            added_dids = set()
            for _, did, dev in _iter_config_devices(cfg):
                if dev.get("provider") == "xiaomi_cloud":
                    added_dids.add(did)
            for d in r.get("devices", []):
                d["added"] = d["did"] in added_dids
            result = r
    except Exception as e:
        result = {"error": str(e)}

elif cmd.startswith("xiaomi_add "):
    try:
        import base64
        data = json.loads(base64.b64decode(cmd[11:]).decode("utf-8"))
        cfg = load_config()
        cfg.setdefault("devices", {})
        cfg["devices"].setdefault("xiaomi_cloud", {})
        
        added = []
        skipped = []
        for d in data:
            did = d.get("did", "")
            if not did:
                continue
            if did in cfg["devices"]["xiaomi_cloud"]:
                skipped.append(did)
                continue
            
            model = d.get("model", "")
            # 自动拉取该型号的 siid/piid spec
            spec = None
            try:
                from acnexus_core.xiaomi_control import fetch_spec_for_model
                spec = fetch_spec_for_model(model)
            except Exception:
                pass
            
            cfg["devices"]["xiaomi_cloud"][did] = {
                "did": did, "model": model,
                "name": model, "token": d.get("token", ""),
                "host": d.get("localip", ""), "port": 80,
                "brand": "xiaomi_cloud", "fan": "auto",
                "schedule_enabled": True, "auto_adjust": True,
                "temp_rules": None,
                "miot_spec": spec,
            }
            added.append(did)
        
        # 去重命名
        all_names = set()
        for _, _, dev in _iter_config_devices(cfg):
            all_names.add(dev.get("name", ""))
        for did in added:
            dev = cfg["devices"]["xiaomi_cloud"][did]
            base_name = dev["model"]
            name = base_name
            i = 2
            while name in all_names:
                name = f"{base_name} ({i})"
                i += 1
            dev["name"] = name
            all_names.add(name)
            if not cfg.get("current_device_mac"):
                cfg["current_device_mac"] = did
        
        save_config(cfg)
        result = {"ok": True, "added": added, "skipped": skipped}
    except Exception as e:
        result = {"error": str(e)}

print(json.dumps(result, ensure_ascii=False, default=str))
