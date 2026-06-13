#!/usr/bin/env python3
"""BroadlinkAC IPK 构建脚本
输出: broadlinkac_3.2-1_all.ipk
"""

import tarfile, io, os, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'broadlinkac', 'files')
BUILD = os.path.join(ROOT, 'ipk_build')
OUT = os.path.join(ROOT, 'broadlinkac_3.2-1_all.ipk')

# ── 清理 ──
if os.path.exists(BUILD):
    shutil.rmtree(BUILD)
if os.path.exists(OUT):
    os.remove(OUT)

os.makedirs(f'{BUILD}/control')
os.makedirs(f'{BUILD}/data')

# ── debian-binary ──
with open(f'{BUILD}/debian-binary', 'w') as f:
    f.write('2.0\n')

# ── control 文件 ──
with open(f'{BUILD}/control/control', 'w') as f:
    f.write(
        'Package: broadlinkac\n'
        'Version: 3.2-1\n'
        'Depends: python3-light, python3-schedule\n'
        'Architecture: all\n'
        'Maintainer: oywq00008-cell\n'
        'License: MIT\n'
        'Description: AI-powered smart AC controller for Broadlink RM.\n'
    )

with open(f'{BUILD}/control/postinst', 'w') as f:
    f.write('#!/bin/sh\nexit 0\n')
os.chmod(f'{BUILD}/control/postinst', 0o755)

# ── 复制数据文件（跳过垃圾）──
SKIP = {'__pycache__'}
SKIP_EXT = {'.ipk', '.run', '.pyc', '.bak', '.pyo'}
for item in os.listdir(SRC):
    if item in SKIP or any(item.endswith(ext) for ext in SKIP_EXT):
        continue
    src = os.path.join(SRC, item)
    dst = os.path.join(BUILD, 'data', item)
    if os.path.isdir(src):
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.ipk', '*.run'))
    else:
        shutil.copy2(src, dst)

# ── 辅助：添加目录条目 ──
def add_dir(tf, name):
    ti = tarfile.TarInfo(name)
    ti.type = tarfile.DIRTYPE
    ti.mode = 0o755
    ti.uid = ti.gid = ti.mtime = 0
    ti.uname = ti.gname = 'root'
    tf.addfile(ti, io.BytesIO(b''))

# ── control.tar.gz（成员名无 ./ 前缀！）──
cbuf = io.BytesIO()
with tarfile.open(fileobj=cbuf, mode='w:gz', format=tarfile.GNU_FORMAT) as tf:
    for fn in ['control', 'postinst']:
        path = f'{BUILD}/control/{fn}'
        ti = tf.gettarinfo(path, fn)
        ti.uid = ti.gid = ti.mtime = 0
        ti.uname = ti.gname = 'root'
        with open(path, 'rb') as f:
            tf.addfile(ti, f)

# ── data.tar.gz ──
dbuf = io.BytesIO()
with tarfile.open(fileobj=dbuf, mode='w:gz', format=tarfile.GNU_FORMAT) as tf:
    for r, ds, fs in os.walk(f'{BUILD}/data'):
        for d in ds:
            arc = os.path.relpath(os.path.join(r, d), f'{BUILD}/data')
            add_dir(tf, f'{arc}/')
        for fn in fs:
            path = os.path.join(r, fn)
            arc = os.path.relpath(path, f'{BUILD}/data')
            ti = tf.gettarinfo(path, arc)
            ti.uid = ti.gid = ti.mtime = 0
            ti.uname = ti.gname = 'root'
            if 'init.d' in arc or 'broadlinkac_service.py' in arc or arc.endswith('.sh') or arc.endswith('.cgi'):
                ti.mode = 0o755
            with open(path, 'rb') as f:
                tf.addfile(ti, f)

# ── 外层 IPK（gzip 压缩！）──
cbuf.seek(0)
dbuf.seek(0)
deb = open(f'{BUILD}/debian-binary', 'rb').read()

with tarfile.open(OUT, 'w:gz', format=tarfile.GNU_FORMAT) as tf:
    for name, content in [('debian-binary', deb), ('control.tar.gz', cbuf.read()), ('data.tar.gz', dbuf.read())]:
        ti = tarfile.TarInfo(name)
        ti.size = len(content)
        ti.uid = ti.gid = ti.mtime = 0
        ti.uname = ti.gname = 'root'
        tf.addfile(ti, io.BytesIO(content))

# ── 清理 ──
shutil.rmtree(BUILD)

print(f'Done: {OUT} ({os.path.getsize(OUT)//1024} KB)')
