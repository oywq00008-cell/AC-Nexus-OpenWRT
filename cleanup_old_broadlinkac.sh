#!/bin/sh
# AC-Nexus-OpenWRT 旧版清理脚本
# 用法: SSH 登录路由器后执行 bash /path/to/cleanup_old_broadlinkac.sh
# 说明: 一键清除旧 BroadlinkAC / AC-Nexus 插件和配置，清理后可直接安装新版 IPK

echo "========================================"
echo "  AC-Nexus-OpenWRT 旧版清理工具"
echo "========================================"
echo ""

# 停止旧服务
echo "[1/5] 停止旧服务..."
/etc/init.d/broadlinkac stop 2>/dev/null || true
/etc/init.d/acnexus stop 2>/dev/null || true
/etc/init.d/acnexus disable 2>/dev/null || true

# 删除旧插件文件
echo "[2/5] 删除旧插件文件..."
rm -rf /usr/lib/broadlinkac /usr/lib/acnexus
rm -f /usr/lib/lua/luci/controller/broadlinkac.lua /usr/lib/lua/luci/controller/acnexus.lua
rm -f /usr/lib/lua/luci/model/cbi/broadlinkac.lua /usr/lib/lua/luci/model/cbi/acnexus.lua
rm -rf /usr/lib/lua/luci/view/broadlinkac /usr/lib/lua/luci/view/acnexus
rm -f /www/cgi-bin/broadlinkac.cgi /www/cgi-bin/acnexus.cgi
rm -f /etc/init.d/broadlinkac /etc/init.d/acnexus
rm -f /etc/config/broadlinkac /etc/config/acnexus
rm -f /etc/uci-defaults/99-broadlinkac /etc/uci-defaults/99-acnexus
rm -rf /usr/share/broadlinkac /usr/share/acnexus

# 清理 overlay 残留
rm -rf /overlay/upper/usr/lib/lua/luci/view/acnexus /overlay/upper/usr/lib/broadlinkac
rm -rf /overlay/upper/usr/lib/acnexus /overlay/upper/usr/lib/broadlinkac
rm -f /tmp/acnexus_* /tmp/broadlinkac_*

# 清理旧配置
echo "[3/5] 清理旧配置..."
rm -rf /root/.ac_controller
rm -f /root/.ac_controller/config.json /root/.ac_controller/device.json /root/.ac_controller/MEMORY.md 2>/dev/null
rm -rf /root/.ac_controller

# 清理 UCI
echo "[4/5] 清理 UCI 配置..."
uci delete acnexus.@device 2>/dev/null
uci delete acnexus.settings 2>/dev/null
uci delete broadlinkac.@device 2>/dev/null
uci delete broadlinkac.settings 2>/dev/null
uci commit acnexus 2>/dev/null
uci commit broadlinkac 2>/dev/null

# 清理 LuCI 缓存
echo "[5/5] 清理 LuCI 缓存..."
rm -f /tmp/luci-indexcache*
rm -rf /tmp/luci-modulecache/* 2>/dev/null
sync

echo ""
echo "========================================"
echo "  清理完成！"
echo ""
echo "  下一步: 在 LuCI 系统 → 软件包 → 上传 acnexus_*.ipk"
echo "========================================"
echo ""
