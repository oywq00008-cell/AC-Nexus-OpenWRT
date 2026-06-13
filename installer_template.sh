#!/bin/sh
# ────────────────────────────────────────────
# BroadlinkAC .run 自解压安装包
# 用法: 上传到路由器 /tmp，然后 bash broadlinkac.run
# ────────────────────────────────────────────

set -e

ARCHIVE=$(awk '/^__ARCHIVE__$/ {print NR+1; exit}' "$0")
WORKDIR="${TMPDIR:-/tmp}/broadlinkac_install"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
tail -n +"$ARCHIVE" "$0" | tar xz -C "$WORKDIR"

echo ""
echo "====== BroadlinkAC 一键安装 ======"
echo ""

echo "[1/3] 安装系统依赖..."
opkg update 2>/dev/null || true
opkg install python3-light python3-broadlink python3-schedule 2>/dev/null || true

echo "[2/3] 安装插件文件..."
cd "$WORKDIR"
cp -r usr/* /usr/ 2>/dev/null || true
cp -r etc/* /etc/ 2>/dev/null || true
chmod +x /etc/init.d/broadlinkac 2>/dev/null || true
chmod +x /etc/uci-defaults/99-broadlinkac 2>/dev/null || true
chmod +x /www/cgi-bin/broadlinkac.cgi 2>/dev/null || true
rm -f /tmp/luci-indexcache*

echo "[3/3] 启动服务..."
/etc/init.d/broadlinkac enable 2>/dev/null || true
/etc/init.d/broadlinkac start 2>/dev/null || true

rm -rf "$WORKDIR"

LAN_IP=$(uci get network.lan.ipaddr 2>/dev/null || echo "你的路由器IP")
echo ""
echo "====== 安装完成 ======"
echo "浏览器打开: http://${LAN_IP}/cgi-bin/luci/admin/services/broadlinkac"
echo ""

exit 0
__ARCHIVE__
