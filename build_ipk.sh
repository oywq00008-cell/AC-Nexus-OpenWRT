#!/bin/sh
# 构建 BroadlinkAC .ipk 安装包
# 输出: broadlinkac_3.2-1_aarch64_cortex-a53.ipk

set -e
cd "$(dirname "$0")"

BUILD="ipk_build"
rm -rf "$BUILD"

# ── 目录结构 ──
mkdir -p "$BUILD/control" "$BUILD/data"

# ── debian-binary ──
echo "2.0" > "$BUILD/debian-binary"

# ── control 文件 ──
cat > "$BUILD/control/control" << 'CTRL'
Package: broadlinkac
Version: 3.2-1
Depends: python3-light, python3-broadlink, python3-schedule
Architecture: aarch64_cortex-a53
Maintainer: oywq00008-cell
License: MIT
Description: AI-powered smart AC controller for Broadlink RM.
CTRL
cat > "$BUILD/control/postinst" << 'POST'
#!/bin/sh
exit 0
POST
chmod +x "$BUILD/control/postinst"

# ── 复制数据文件 ──
cp -r broadlinkac/files/* "$BUILD/data/"

# ── Python 构建（避免 macOS BSD tar 兼容问题）──
python3 << 'PYEOF'
import tarfile, io, os

root = 'ipk_build'
os.chdir(root)

def add_dir(tf, name):
    ti = tarfile.TarInfo(name)
    ti.type = tarfile.DIRTYPE
    ti.mode = 0o755
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = 'root'
    tf.addfile(ti, io.BytesIO(b''))

# control.tar.gz
cbuf = io.BytesIO()
with tarfile.open(fileobj=cbuf, mode='w:gz', format=tarfile.GNU_FORMAT) as tf:
    add_dir(tf, './')
    for fn in ['control', 'postinst']:
        path = f'control/{fn}'
        if os.path.exists(path):
            ti = tf.gettarinfo(path, f'./{fn}')
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = 'root'
            with open(path, 'rb') as f:
                tf.addfile(ti, f)
cbuf.seek(0)

# data.tar.gz
dbuf = io.BytesIO()
with tarfile.open(fileobj=dbuf, mode='w:gz', format=tarfile.GNU_FORMAT) as tf:
    add_dir(tf, './')
    for r, ds, fs in os.walk('data'):
        for d in ds:
            arc = os.path.relpath(os.path.join(r, d), 'data')
            add_dir(tf, f'./{arc}/')
        for fn in fs:
            path = os.path.join(r, fn)
            arc = os.path.relpath(path, 'data')
            ti = tf.gettarinfo(path, f'./{arc}')
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = 'root'
            if 'init.d' in arc or 'broadlinkac_service.py' in arc or arc.endswith('.sh') or arc.endswith('.cgi'):
                ti.mode = 0o755
            with open(path, 'rb') as f:
                tf.addfile(ti, f)
dbuf.seek(0)

# 合并为 ipk（无 ./ 前缀！）
with tarfile.open('../../broadlinkac_3.2-1_aarch64_cortex-a53.ipk', 'w:gz', format=tarfile.GNU_FORMAT) as tf:
    ti = tarfile.TarInfo('debian-binary')
    ti.size = 4
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = 'root'
    tf.addfile(ti, io.BytesIO(b'2.0\n'))
    
    ti = tarfile.TarInfo('control.tar.gz')
    ti.size = cbuf.getbuffer().nbytes
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = 'root'
    tf.addfile(ti, cbuf)
    
    ti = tarfile.TarInfo('data.tar.gz')
    ti.size = dbuf.getbuffer().nbytes
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = 'root'
    tf.addfile(ti, dbuf)

PYEOF

SIZE=$(du -h broadlinkac_3.2-1_aarch64_cortex-a53.ipk | cut -f1)
echo "Done: broadlinkac_3.2-1_aarch64_cortex-a53.ipk (${SIZE})"
