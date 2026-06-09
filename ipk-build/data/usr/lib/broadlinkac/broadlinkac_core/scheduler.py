"""BroadlinkAC Core — 定时任务"""

import time
import threading
from datetime import datetime
import schedule as sch

import broadlinkac_core.config as _cfg

from broadlinkac_core.weather import fetch_weather
from broadlinkac_core.ac_control import send_ac, decide_ac, MODE_KEYS
from broadlinkac_core.logger import write_log, get_last_ac_state

_sched_lock = threading.Lock()


def _device_online(mac):
    """判断设备最近是否在线"""
    return not _cfg._online_macs or mac in _cfg._online_macs


def scheduled_job(mac):
    dev = _cfg.config.get("devices", {}).get(mac, {})
    name = dev.get("name", mac[:8])
    if not _device_online(mac):
        write_log("系统", f"⏰ [{name}] 定时触发 → 设备离线，跳过")
        return None
    if _cfg._cached_temp is None:
        w = fetch_weather()
        if not w:
            return None
        outdoor = float(w["temp"])
    else:
        outdoor = _cfg._cached_temp

    target, mode = decide_ac(outdoor, mac)
    if mode == "off":
        name = dev.get("name", mac[:8])
        write_log("空调", f"⏰ [{name}] 定时触发: 室外 {outdoor}°C → 关闭，不发送指令")
        return None

    # 台风保护：风暴 < 100km 时不启动空调
    from broadlinkac_core.typhoon import typhoon_threat_distance
    min_dist, storm_name = typhoon_threat_distance()
    if min_dist < 100:
        write_log("系统",
                  f"⏰ [{name}] 定时触发: 风暴 {storm_name} 距 {min_dist}km，跳过开机")
        return None

    try:
        result = send_ac("on", mode, target, "auto", source="定时", mac=mac)
        write_log("空调", result)
        return result
    except Exception as e:
        write_log("系统", f"定时发送失败: {e}")
    return None


def scheduled_off_job(mac):
    """定时关机"""
    dev = _cfg.config.get("devices", {}).get(mac, {})
    name = dev.get("name", mac[:8])
    if not _device_online(mac):
        write_log("系统", f"⏰ [{name}] 定时关机 → 设备离线，跳过")
        return None
    # 检测空调状态：已关则跳过
    state = get_last_ac_state()
    if state["power"] == "off":
        return None
    # 台风保护：已被台风关机的跳过
    from broadlinkac_core.typhoon import typhoon_threat_distance
    min_dist, _ = typhoon_threat_distance()
    if min_dist < 100:
        write_log("系统", f"⏰ [{name}] 定时关机 → 风暴已处理，跳过")
        return None

    try:
        result = send_ac("off", "cool", 26, "auto", source="定时", mac=mac)
        write_log("空调", result)
        return result
    except Exception as e:
        write_log("系统", f"定时关机失败: {e}")
    return None


def auto_adjust_job(mac):
    """每2小时自动调温：读日志判状态 → 跑规则 → 温度无变化则跳过

    拦截规则：
    - 台风 < 100km → 跳过（信任 30min 巡检已强制关过，避免发开机打脸）
    - 空调 power=off → 跳过（用户主动关了就不打扰）
    - 其余路径：读天气 → 跑规则 → 改模式/温度就发码，不变就跳过
    """
    dev = _cfg.config.get("devices", {}).get(mac, {})
    name = dev.get("name", mac[:8])
    if not _device_online(mac):
        write_log("系统", f"🔄 [{name}] 自动调温 → 设备离线，跳过")
        return

    # 台风 < 100km：跳过（30min 巡检会强制关空调，这里开机是反行为）
    from broadlinkac_core.typhoon import typhoon_threat_distance
    min_dist, storm_name = typhoon_threat_distance()
    if min_dist < 100:
        write_log("系统", f"🔄 [{name}] 自动调温: 风暴 {storm_name} 距 {min_dist}km，跳过")
        return

    # 空调已关：跳过
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

    target, mode = decide_ac(outdoor, mac)
    if mode == "off":
        write_log("空调", send_ac("off", "cool", 26, "auto", source="自动", mac=mac))
        return

    if state["mode"] == mode and state["temp"] == target:
        write_log("空调", f"[{datetime.now():%H:%M}] [{name}] 自动调温 → 不更改温度")
        return

    try:
        write_log("空调", send_ac("on", mode, target, "auto", source="自动", mac=mac))
    except Exception as e:
        write_log("系统", f"自动调温失败: {e}")


def register_all_jobs():
    """注册所有设备的 AC 定时任务（在 _sched_lock 内调用）

    设计说明：
    - scheduled_job / scheduled_off_job：用户指定具体时间，固定触发
    - auto_adjust_job：每 2 小时相对间隔触发（开机后 2h、4h、6h…）
      用 `sch.every(2).hours` 而不是固定整点，因为用户活动时间不固定
      （有人 6 点起床、有人 14 点活动、有人凌晨加班），全天 24h 都可能需要
      相对间隔 = "从上次执行算起 2 小时"，自然贴合空调使用场景
      schedule 库底层在 `run_pending()` 后会更新 last_run，
      scheduler_loop 用 `sch.idle_seconds()` 精确计算下次等待时间
    """
    sch.clear()
    for mac, dev in _cfg.config.get("devices", {}).items():
        if dev.get("schedule_enabled", True):
            sch.every().day.at(dev.get("trigger_time", "12:00")).do(scheduled_job, mac=mac)
        if dev.get("off_enabled"):
            sch.every().day.at(dev.get("off_time", "22:00")).do(scheduled_off_job, mac=mac)
        if dev.get("auto_adjust", True):
            # 相对间隔 2 小时（不是固定整点）—— 关机时 auto_adjust_job 内部
            # 读日志判 power=off 直接 return，下次循环照常推进
            sch.every(2).hours.do(auto_adjust_job, mac=mac)


def scheduler_loop():
    """任务循环：每次 run_pending() 后用 sch.idle_seconds() 精确睡眠

    schedule 库会在 run_pending() 中：
    - 触发所有到期任务
    - 更新每个 job 的 last_run
    - idle_seconds() 返回「最近 job 触发 → 下次 job 触发」的精确秒数

    所以 auto_adjust_job 即使 power=off 提前 return，循环时间也照常推进
    （这正是用户要求的行为：开启了就按 2h 节奏跑，关机状态就跳过）
    """
    register_all_jobs()
    while True:
        with _sched_lock:
            sch.run_pending()
        idle = sch.idle_seconds()
        # idle_seconds() 可能为 None（库刚启动还没算过）或负数
        # 兜底 15s 防止空转 CPU
        sleep_sec = max(idle, 0) if idle is not None else 15
        time.sleep(sleep_sec)


_sched_started = False
_data_loops_started = False


def start_scheduler():
    """启动后台调度线程（幂等，仅首次调用生效）"""
    global _sched_started
    if _sched_started:
        return
    _sched_started = True
    threading.Thread(target=scheduler_loop, daemon=True).start()


def re_register():
    """设备增删后让 schedule 库立即重读 config（在 _sched_lock 内）"""
    with _sched_lock:
        register_all_jobs()


# ── 数据独立循环（与 schedule 库完全隔离）──

def _weather_loop():
    """每 10 分钟拉一次天气 → 写入 _cfg._cached_temp

    首次先 sleep 一轮：init() 已立即拉过一次，避免重复拉取。
    拉到的数据同时通过 _set_last_weather 写一份给 fetch_weather 兜底用。
    """
    import time
    while True:
        time.sleep(600)
        try:
            w = fetch_weather()
            if w and w.get("temp"):
                _cfg._cached_temp = float(w["temp"])
            # 不管成功失败，都尝试更新兜底缓存（让 _last_weather 始终是最近一次成功值）
            if w:
                from broadlinkac_core.weather import _set_last_weather
                _set_last_weather(w)
        except Exception as e:
            try:
                from broadlinkac_core.logger import write_log
                write_log("系统", f"天气拉取失败: {e}")
            except Exception:
                pass


def _typhoon_loop():
    """每 30 分钟拉一次台风 → 判定 < 100km 强制关全部

    首次先 sleep 一轮：init() 已立即拉过一次，避免重复拉取与重复判定。

    judge_and_shutdown 现在不用维护 ty_ac_off_sent 标志位了，
    每次循环内部读 get_last_ac_state() 查真实状态决定要不要发码。
    """
    import time
    from broadlinkac_core.typhoon import fetch_and_cache
    from broadlinkac_core.logger import write_log
    while True:
        time.sleep(1800)
        try:
            fetch_and_cache()
            _cfg.typhoon_judge_and_shutdown(write_log)
        except Exception as e:
            try:
                write_log("系统", f"台风拉取失败: {e}")
            except Exception:
                pass


def start_data_loops():
    """启动天气/台风独立后台循环（幂等）"""
    global _data_loops_started
    if _data_loops_started:
        return
    _data_loops_started = True
    # 让定时开关机/调温也能用上数据
    import broadlinkac_core.config as _cfg
    _cfg.typhoon_judge_and_shutdown = __import__(
        "broadlinkac_core.typhoon", fromlist=["judge_and_shutdown"]
    ).judge_and_shutdown
    threading.Thread(target=_weather_loop, daemon=True).start()
    threading.Thread(target=_typhoon_loop, daemon=True).start()
