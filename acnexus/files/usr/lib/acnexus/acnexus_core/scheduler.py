"""AC-Nexus-OpenWRT Core — 定时任务"""

import time
import threading
from datetime import datetime
import schedule as sch

import acnexus_core.config as _cfg

from acnexus_core.weather import fetch_weather
from acnexus_core.ac_control import send_ac, decide_ac, MODE_KEYS
from acnexus_core.logger import write_log, get_last_ac_state

_sched_lock = threading.RLock()
_sched_paused = False
_last_sched_sig = None  # 调度配置签名，用于变更检测


def pause_scheduler():
    global _sched_paused
    _sched_paused = True


def resume_scheduler():
    global _sched_paused
    _sched_paused = False


# ── 多品牌设备迭代 ──

def _iter_all_devices():
    """遍历 {broadlink: {mac: dev}, xiaomi_cloud: {did: dev}} → (provider, device_id, device)"""
    devs = _cfg.config.get("devices", {})
    for provider, provider_devs in devs.items():
        if not isinstance(provider_devs, dict):
            continue
        for device_id, dev in provider_devs.items():
            yield provider, device_id, dev


def _find_device(device_id):
    """跨所有品牌查找设备，返回 (provider, device_dict)，找不到返回 (\"broadlink\", {})"""
    for provider, _, dev in _iter_all_devices():
        if device_id == dev.get("mac", "") or device_id == dev.get("did", ""):
            return provider, dev
    return "broadlink", {}


def _device_online(provider, device_id):
    """判断设备最近是否在线。MIoT 设备始终视为在线。"""
    if provider == "xiaomi_cloud":
        return True
    return not _cfg._online_macs or device_id in _cfg._online_macs


# ── 定时任务 ──

def scheduled_job(device_id):
    provider, dev = _find_device(device_id)
    name = dev.get("name", device_id[:8])
    if not _device_online(provider, device_id):
        write_log("系统", f"⏰ [{name}] 定时触发 → 设备离线，跳过")
        return None
    if _cfg._cached_temp is None:
        w = fetch_weather()
        if not w:
            return None
        outdoor = float(w["temp"])
    else:
        outdoor = _cfg._cached_temp

    target, mode = decide_ac(outdoor, device_id)
    if mode == "off":
        write_log("空调", f"⏰ [{name}] 定时触发: 室外 {outdoor}°C → 关闭，不发送指令")
        return None

    if _sched_paused:
        write_log("系统", f"⏰ [{name}] 定时触发: 风暴保护已生效，跳过")
        return None

    try:
        result = send_ac("on", mode, target, "auto", source="定时", mac=device_id)
        # send_ac 返回的日志格式已包含 [HH:MM]，直接写入
        write_log("空调", result)
        return result
    except Exception as e:
        write_log("系统", f"定时发送失败: {e}")
    return None


def scheduled_off_job(device_id):
    provider, dev = _find_device(device_id)
    name = dev.get("name", device_id[:8])
    if not _device_online(provider, device_id):
        write_log("系统", f"⏰ [{name}] 定时关机 → 设备离线，跳过")
        return None
    state = get_last_ac_state()
    if state["power"] == "off":
        return None
    if _sched_paused:
        return None

    try:
        now = datetime.now()
        result = send_ac("off", "cool", 26, "auto", source="定时", mac=device_id)
        # send_ac 返回的日志格式已包含 [HH:MM]，直接写入
        write_log("空调", result)
        return result
    except Exception as e:
        write_log("系统", f"定时关机失败: {e}")
    return None


def auto_adjust_job(device_id):
    provider, dev = _find_device(device_id)
    name = dev.get("name", device_id[:8])
    if not _device_online(provider, device_id):
        write_log("系统", f"🔄 [{name}] 自动调温 → 设备离线，跳过")
        return
    state = get_last_ac_state()
    if state["power"] == "off":
        return

    if _cfg._cached_temp is None:
        w = fetch_weather()
        if not w:
            write_log("系统", f"🔄 [{name}] 自动调温: 天气获取失败，跳过")
            return
        outdoor = float(w["temp"])
    else:
        outdoor = _cfg._cached_temp

    target, mode = decide_ac(outdoor, device_id)
    if mode == "off":
        write_log("空调", send_ac("off", "cool", 26, "auto", source="自动", mac=device_id))
        return

    if state["mode"] == mode and state["temp"] == target:
        write_log("空调", f"[{datetime.now():%H:%M}] [{name}] 自动调温 → 不更改温度")
        return

    try:
        write_log("空调", send_ac("on", mode, target, "auto", source="自动", mac=device_id))
    except Exception as e:
        write_log("系统", f"自动调温失败: {e}")


def _scheduled_on_wrapper(device_id, days):
    if datetime.now().isoweekday() in days:
        return scheduled_job(device_id)


def _scheduled_off_wrapper(device_id, days):
    if datetime.now().isoweekday() in days:
        return scheduled_off_job(device_id)


# ── 配置迁移 ──

# ── 任务注册 ──

def _compute_sched_sig():
    """计算当前调度配置签名。签名相同时跳过重建，避免 every(N).hours 计时被重置。"""
    import json as _json
    templates = _cfg.config.get("schedule_templates", {}) or {}
    if not isinstance(templates, dict):
        templates = {}
    sig = {}
    for provider, device_id, dev in _iter_all_devices():
        tmpl_name = dev.get("active_template", "")
        sig[device_id] = {
            "schedule_enabled": dev.get("schedule_enabled", False),
            "auto_adjust": dev.get("auto_adjust", False),
            "active_template": tmpl_name,
            "tmpl_hash": _json.dumps(templates.get(tmpl_name, {}), sort_keys=True, default=str),
        }
    return _json.dumps(sig, sort_keys=True, ensure_ascii=False, default=str)


def register_all_jobs():
    global _last_sched_sig
    with _sched_lock:
        sig = _compute_sched_sig()
        if sig == _last_sched_sig:
            return
        _last_sched_sig = sig
        sch.clear()
        templates = _cfg.config.get("schedule_templates", {}) or {}
        if not isinstance(templates, dict):
            templates = {}
        for provider, device_id, dev in _iter_all_devices():
            tmpl_name = dev.get("active_template")
            tmpl = templates.get(tmpl_name) if tmpl_name else None
            if tmpl and dev.get("schedule_enabled", False):
                groups = tmpl.get("groups", [])
                for grp in groups:
                    days = set(grp.get("days", []))
                    for slot in grp.get("slots", []):
                        on_t = slot.get("on")
                        off_t = slot.get("off")
                        if on_t and slot.get("on_enabled", True):
                            sch.every().day.at(on_t).do(_scheduled_on_wrapper, device_id=device_id, days=days)
                        if off_t and slot.get("off_enabled", True):
                            sch.every().day.at(off_t).do(_scheduled_off_wrapper, device_id=device_id, days=days)
            if dev.get("auto_adjust", False):
                sch.every(2).hours.do(auto_adjust_job, device_id=device_id)


def re_register():
    """外部 API 调用：用户修改设置后重建所有定时任务"""
    try:
        register_all_jobs()
    except Exception as e:
        print(f"[scheduler] re_register 失败: {e}", file=__import__("sys").stderr)


# ── 主循环 + 启动 ──

def scheduler_loop():
    register_all_jobs()
    while True:
        if not _cfg.config.get("enabled", True):
            time.sleep(30)
            continue
        with _sched_lock:
            if not _sched_paused:
                sch.run_pending()
        idle = sch.idle_seconds()
        time.sleep(min(max(idle or 0, 0), 30))  # 最长 30s，确保 enabled 检测及时


_sched_started = False


def start_scheduler():
    global _sched_started
    if _sched_started:
        return
    _sched_started = True
    threading.Thread(target=scheduler_loop, daemon=True).start()


_data_started = False

def start_data_loops():
    global _data_started
    if _data_started:
        return
    _data_started = True
    threading.Thread(target=_weather_loop, daemon=True).start()
    threading.Thread(target=_typhoon_loop, daemon=True).start()


def _weather_loop():
    import time
    while True:
        if not _cfg.config.get("enabled", True):
            time.sleep(30)
            continue
        try:
            from acnexus_core.weather import fetch_weather
            w = fetch_weather()
            if w and w.get("temp"):
                _cfg._cached_temp = float(w["temp"])
        except Exception:
            pass
        time.sleep(600)


def _typhoon_loop():
    import time
    while True:
        if not _cfg.config.get("enabled", True):
            time.sleep(30)
            continue
        try:
            from acnexus_core.typhoon import fetch_and_cache, judge_and_shutdown
            from acnexus_core.logger import write_log
            fetch_and_cache()
            judge_and_shutdown(write_log)
        except Exception:
            pass
        time.sleep(1800)
