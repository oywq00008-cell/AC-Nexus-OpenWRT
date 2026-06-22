#!/bin/sh
# ============================================================
# AC-Nexus-OpenWRT OpenWRT 安装指南
#
# 方法一 (推荐): LuCI 网页上传 .ipk
#   → 路由器网页: 系统 → 软件包 → 上传软件包
#   → 选择 acnexus_*.ipk 即可，依赖自动安装
#
# 方法二 (兜底): .run 脚本一键安装
#   → 适用于代理/DNS 导致 ipk 安装失败的情况
#   → bash acnexus_*.run
#
# 前提: 路由器已联网
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IPK="$(ls "$SCRIPT_DIR"/acnexus_*.ipk 2>/dev/null | head -1)"
RUNFILE="$(ls "$SCRIPT_DIR"/acnexus_*.run 2>/dev/null | head -1)"

echo "========================================="
echo "   AC-Nexus-OpenWRT OpenWRT 安装器"
echo "========================================="
echo ""

if [ -n "$IPK" ]; then
    echo ">>> 方法一 (推荐): LuCI 网页上传 ipk"
    echo ""
    echo "  1. 浏览器打开路由器后台"
    echo "  2. 系统 → 软件包 → 上传软件包"
    echo "  3. 选择: $(basename "$IPK")"
    echo "  4. 等待安装完成，刷新页面即可"
    echo ""
fi

if [ -n "$RUNFILE" ]; then
    echo ">>> 方法二 (兜底): .run 脚本安装"
    echo ""
    echo "  如果方法一失败，请用此方法:"
    echo "  scp $(basename "$RUNFILE") root@路由器IP:/tmp/"
    echo "  ssh root@路由器IP"
    echo "  bash /tmp/$(basename "$RUNFILE")"
    echo ""
fi

echo "========================================="
