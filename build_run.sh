#!/bin/sh
# 构建 AC-Nexus-OpenWRT .run 自解压安装包
# 现在主用 Python 构建以避免 Windows tar 兼容问题
# 保留此脚本作为备选（需 Git Bash）

set -e
cd "$(dirname "$0")"

echo "打包插件文件..."
tar czf data.tar.gz -C acnexus/files .

echo "生成 .run..."
cp installer_template.sh acnexus_3.2-1.run
cat data.tar.gz >> acnexus_3.2-1.run
chmod +x acnexus_3.2-1.run

rm -f data.tar.gz

SIZE=$(wc -c acnexus_3.2-1.run | awk '{print $1}')
echo "Done: acnexus_3.2-1.run (${SIZE} bytes)"
echo "提示: Windows 上建议用 python build_run.py 代替此脚本构建"
