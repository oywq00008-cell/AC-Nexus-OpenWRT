#!/bin/sh
# AC-Nexus-OpenWRT 旧版清理脚本
# 用法: SCP 到路由器，bash cleanup_old_broadlinkac.sh
# 说明: 清除旧 BroadlinkAC 插件和配置文件，然后安装新版 AC-Nexus-OpenWRT

echo "========================================"
echo "  AC-Nexus-OpenWRT 旧版清理工具"
echo "========================================"
echo ""

# 停止旧服务
echo "[1/4] 停止旧服务..."
/etc/init.d/broadlinkac stop 2>/dev/null || true
/etc/init.d/acnexus stop 2>/dev/null || true
killall python3 2>/dev/null || true

# 删除旧插件文件（broadlinkac 旧名 + acnexus 新名）
echo "[2/4] 删除旧插件文件..."
rm -rf /usr/lib/broadlinkac /usr/lib/acnexus
rm -f /usr/lib/lua/luci/controller/broadlinkac.lua /usr/lib/lua/luci/controller/acnexus.lua
rm -f /usr/lib/lua/luci/model/cbi/broadlinkac.lua /usr/lib/lua/luci/model/cbi/acnexus.lua
rm -rf /usr/lib/lua/luci/view/broadlinkac /usr/lib/lua/luci/view/acnexus
rm -f /www/cgi-bin/broadlinkac.cgi /www/cgi-bin/acnexus.cgi
rm -f /etc/init.d/broadlinkac /etc/init.d/acnexus
rm -f /etc/config/broadlinkac /etc/config/acnexus
rm -f /etc/uci-defaults/99-broadlinkac /etc/uci-defaults/99-acnexus
rm -rf /usr/share/broadlinkac /usr/share/acnexus

# 清理旧配置文件
echo "[3/4] 清理旧配置..."
rm -f /root/.ac_controller/config.json
rm -f /root/.ac_controller/device.json
rm -f /root/.ac_controller/MEMORY.md

# 清理 LuCI 缓存
echo "[4/4] 清理 LuCI 缓存..."
rm -rf /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/*

echo ""
echo "========================================"
echo "  清理完成！现在可以安装新版 AC-Nexus-OpenWRT"
echo "========================================"
echo ""
echo "  方法一 (推荐): LuCI 系统 → 软件包 → 上传 acnexus_*.ipk"
echo "  方法二: bash acnexus_*.run"
echo ""
