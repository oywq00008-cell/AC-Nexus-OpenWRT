#!/bin/sh
# BroadlinkAC 手动安装脚本
# 用法：bash install_manual.sh <路由器IP>
# 示例：bash install_manual.sh 192.168.8.1
#
# 前置条件：
#   1. macOS/Linux 终端，或 Windows 已安装 OpenSSH
#   2. 路由器已开启 SSH
#   3. 当前目录是项目根目录（包含 broadlinkac/files/）

set -e

ROUTER="${1:-}"
if [ -z "$ROUTER" ]; then
    echo "用法: bash install_manual.sh <路由器IP>"
    echo "示例: bash install_manual.sh 192.168.1.1"
    exit 1
fi

echo "=== BroadlinkAC 手动安装 ==="
echo "目标路由器: $ROUTER"
echo ""

# 1. 上传文件
echo "[1/3] 上传插件文件..."
scp -r broadlinkac/files/* root@${ROUTER}:/tmp/broadlinkac_install/

# 2. 安装
echo "[2/3] 安装到路由器..."
ssh root@${ROUTER} "
set -e
cd /tmp/broadlinkac_install
cp -r usr/* /usr/
cp etc/init.d/broadlinkac /etc/init.d/ && chmod +x /etc/init.d/broadlinkac
cp etc/config/broadlinkac /etc/config/
cp etc/uci-defaults/99-broadlinkac /etc/uci-defaults/ && chmod +x /etc/uci-defaults/99-broadlinkac
chmod +x /www/cgi-bin/broadlinkac.cgi
rm /tmp/luci-indexcache* 2>/dev/null || true

opkg update
opkg install python3-light python3-broadlink python3-schedule 2>/dev/null || true

uci set broadlinkac.settings.enabled='1' && uci commit broadlinkac
/etc/init.d/broadlinkac enable
/etc/init.d/broadlinkac start
"

# 3. 完成
echo "[3/3] 安装完成"
echo ""
echo "浏览器打开: http://${ROUTER}/cgi-bin/luci/admin/services/broadlinkac"
echo ""
