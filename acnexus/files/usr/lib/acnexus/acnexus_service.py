#!/usr/bin/env python3
"""AC-Nexus-OpenWRT OpenWRT service — 后台守护主入口

启动两个独立后台循环：
- 天气：每 10 分钟拉一次，覆盖 _cfg._cached_temp
- 台风：每 30 分钟拉一次，< 100km 强制关全部空调
- 定时任务：每天指定时间触发开关机/自动调温
"""
import sys
sys.path.insert(0, '/usr/lib/acnexus')

from acnexus_core import init
init()

# init() 已经触发了 scheduler 和数据循环；保持进程存活
try:
    import time
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    pass
