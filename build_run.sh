#!/bin/sh
# 构建 BroadlinkAC .run 自解压安装包
# 输出: broadlinkac_3.2-1.run

set -e
cd "$(dirname "$0")"

# 1. 打包项目文件
echo "打包插件文件..."
tar czf data.tar.gz -C broadlinkac/files .

# 2. 拼接：安装脚本 + 数据
echo "生成 .run..."
cp installer_template.sh ../broadlinkac_3.2-1.run
cat data.tar.gz >> ../broadlinkac_3.2-1.run
chmod +x ../broadlinkac_3.2-1.run

# 3. 清理
rm -f data.tar.gz

SIZE=$(du -h ../broadlinkac_3.2-1.run | cut -f1)
echo "Done: broadlinkac_3.2-1.run (${SIZE})"
