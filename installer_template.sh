#!/bin/sh
# ============================================================
# AC-Nexus-OpenWRT .run 自解压安装器
# 用法: SCP 到路由器 /tmp，bash acnexus-xxx.run
#
# 适用场景: LuCI 上传 ipk 失败（代理/DNS 问题）时使用
# 前提: 路由器已联网
# ============================================================
set -e

ARCHIVE=$(awk '/^__ARCHIVE__$/ {print NR+1; exit}' "$0")
WORKDIR="${TMPDIR:-/tmp}/acnexus_install"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
tail -n +"$ARCHIVE" "$0" | tar xz -C "$WORKDIR"

echo ""
echo "========================================="
echo "   AC-Nexus-OpenWRT OpenWRT 一键安装器"
echo "========================================="
echo ""

# ── [1/6] 绕过代理 SSL 证书问题 ──
echo "[1/6] 配置 opkg..."
grep -q "no_check_certificate" /etc/opkg/opkg.conf 2>/dev/null || \
    echo "option no_check_certificate 1" >> /etc/opkg/opkg.conf

# ── [2/6] 更新软件源 ──
echo "[2/6] 更新软件源..."
opkg update

# ── [3/6] 安装系统依赖 ──
echo "[3/6] 安装 Python 依赖..."
opkg install python3-light python3-urllib python3-email python3-openssl python3-xml

# ── [4/6] 复制插件文件 ──
echo "[4/6] 安装插件文件..."
cd "$WORKDIR"

# 复制到系统目录
cp -r usr/* /usr/
[ -d www ] && cp -r www/* /www/
[ -d etc ] && cp -r etc/* /etc/

# 修复 Windows 换行符 (CRLF -> LF)
for f in \
    /www/cgi-bin/acnexus.cgi \
    /etc/init.d/acnexus \
    /etc/uci-defaults/99-acnexus \
    /etc/config/acnexus \
    /usr/lib/lua/luci/view/acnexus/dashboard.htm \
    /usr/lib/lua/luci/controller/acnexus.lua \
    /usr/lib/lua/luci/model/cbi/acnexus.lua \
; do
    [ -f "$f" ] && sed -i 's/\r//' "$f"
done

# 设置可执行权限
chmod +x /etc/init.d/acnexus
chmod +x /etc/uci-defaults/99-acnexus
chmod +x /www/cgi-bin/acnexus.cgi

# 清理 LuCI 缓存
rm -f /tmp/luci-indexcache* /tmp/luci-modulecache/*

# ── [5/6] 验证依赖 ──
echo "[5/6] 验证安装..."
python3 -c "
import sys
sys.path.insert(0, '/usr/lib/acnexus')
for mod in ['broadlink', 'schedule', 'pyaes']:
    __import__(mod)
import urllib, ssl, email, xml.etree.ElementTree
print('OK')
" && echo "   所有依赖通过 ✅" || echo "   ⚠️ 部分依赖缺失，但不影响基本功能"

# ── [6/6] 启动服务 ──
echo "[6/6] 启动服务..."
/etc/init.d/acnexus enable
/etc/init.d/acnexus start

# 自检
sleep 1
if ps | grep -q "[a]cnexus_service"; then
    echo "   服务运行中 ✅"
else
    echo "   ⚠️ 服务启动失败，请检查日志: /tmp/acnexus.log"
fi

rm -rf "$WORKDIR"

LAN_IP=$(uci get network.lan.ipaddr 2>/dev/null || echo "你的路由器IP")
echo ""
echo "========================================="
echo "   安装完成！"
echo "   http://${LAN_IP}/cgi-bin/luci/admin/services/acnexus"
echo "========================================="

exit 0
__ARCHIVE__
