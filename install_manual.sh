#!/bin/sh
# AC-Nexus-OpenWRT 手动安装脚本
# 用法：bash install_manual.sh <路由器IP>
# 示例：bash install_manual.sh 192.168.8.1
#
# 前置条件：
#   1. macOS/Linux 终端，或 Windows 已安装 OpenSSH
#   2. 路由器已开启 SSH
#   3. 当前目录是项目根目录（包含 acnexus/files/）

set -e

ROUTER="${1:-}"
if [ -z "$ROUTER" ]; then
    echo "用法: bash install_manual.sh <路由器IP>"
    echo "示例: bash install_manual.sh 192.168.1.1"
    exit 1
fi

echo "=== AC-Nexus-OpenWRT 手动安装 ==="
echo "目标路由器: $ROUTER"
echo ""

# 1. 上传文件
echo "[1/3] 上传插件文件..."
scp -r acnexus/files/* root@${ROUTER}:/tmp/acnexus_install/

# 2. 安装
echo "[2/3] 安装到路由器..."
ssh root@${ROUTER} "
set -e
cd /tmp/acnexus_install
cp -r usr/* /usr/
cp etc/init.d/acnexus /etc/init.d/ && chmod +x /etc/init.d/acnexus
cp etc/config/acnexus /etc/config/
cp etc/uci-defaults/99-acnexus /etc/uci-defaults/ && chmod +x /etc/uci-defaults/99-acnexus
chmod +x /www/cgi-bin/acnexus.cgi
# 修复可能来自 Windows 用户的 CRLF 换行符
for f in /etc/init.d/acnexus /etc/uci-defaults/99-acnexus /www/cgi-bin/acnexus.cgi /usr/lib/lua/luci/view/acnexus/dashboard.htm /usr/lib/lua/luci/controller/acnexus.lua /usr/lib/lua/luci/model/cbi/acnexus.lua; do
    [ -f "$f" ] && sed -i 's/\r//' "$f"
done
rm /tmp/luci-indexcache* 2>/dev/null || true

grep -q "no_check_certificate" /etc/opkg/opkg.conf 2>/dev/null || \
    echo "option no_check_certificate 1" >> /etc/opkg/opkg.conf
opkg update
opkg install python3-light python3-urllib python3-email python3-openssl python3-xml

uci set acnexus.@acnexus[0].enabled='1' && uci commit acnexus
/etc/init.d/acnexus enable
/etc/init.d/acnexus start
"

# 3. 完成
echo "[3/3] 安装完成"
echo ""
echo "浏览器打开: http://${ROUTER}/cgi-bin/luci/admin/services/acnexus"
echo ""
