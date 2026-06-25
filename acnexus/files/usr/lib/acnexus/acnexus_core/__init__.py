"""AC-Nexus-OpenWRT Core — 公共 API

用法:
    from acnexus_core import init, send_ac

    init(api_key="xxx", qw_host="https://xxx.re.qweatherapi.com")
    send_ac("on", "cool", 26, "auto")
"""

from acnexus_core.config import init
from acnexus_core.ac_control import send_ac
