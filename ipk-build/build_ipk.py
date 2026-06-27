#!/usr/bin/env python3
"""Build IPK in gzip-tar format (OpenWRT 24.10 compatible)"""
import tarfile, io, os, shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Step 0: Sync data
src = '../acnexus/files'
dst = 'data'
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)

# Clean pycache/CRLF
for root, dirs, files in os.walk(dst):
    for d in list(dirs):
        if d == '__pycache__':
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            dirs.remove(d)
    for f in files:
        if f.endswith('.pyc'):
            os.remove(os.path.join(root, f))
for root, dirs, files in os.walk(dst):
    for f in files:
        if any(f.endswith(ext) for ext in ('.py', '.sh', '.lua', '.htm', '.html', '.txt')):
            path = os.path.join(root, f)
            with open(path, 'rb') as fh:
                content = fh.read()
            fixed = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            if fixed != content:
                with open(path, 'wb') as fh: fh.write(fixed)
                print(f'  Fixed CRLF: {os.path.relpath(path, dst)}')
print(f'Synced: {src} -> {dst}')

# Fix CRLF in CONTROL files
for ctrl in ['CONTROL/control', 'CONTROL/postinst']:
    if os.path.exists(ctrl):
        with open(ctrl, 'rb') as fh:
            raw = fh.read()
        fixed = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        if fixed != raw:
            with open(ctrl, 'wb') as fh: fh.write(fixed)
            print(f'  Fixed CRLF: {ctrl}')

# Clean old
for f in ['control.tar.gz', 'data.tar.gz', 'debian-binary']:
    if os.path.exists(f): os.remove(f)

# debian-binary
with open('debian-binary', 'w') as f:
    f.write('2.0\n')

# control.tar.gz (entries WITHOUT ./ prefix!)
with tarfile.open('control.tar.gz', 'w:gz', format=tarfile.USTAR_FORMAT) as tf:
    for fn in ['control', 'postinst']:
        path = f'CONTROL/{fn}'
        if os.path.exists(path):
            info = tf.gettarinfo(path, fn)
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            if fn == 'postinst':
                info.mode = 0o755
            with open(path, 'rb') as fh:
                tf.addfile(info, fh)

# data.tar.gz (entries WITHOUT ./ prefix!)
with tarfile.open('data.tar.gz', 'w:gz', format=tarfile.USTAR_FORMAT) as tf:
    for root, dirs, files in os.walk('data'):
        for d in dirs:
            arc = os.path.relpath(os.path.join(root, d), 'data').replace('\\', '/')
            info = tarfile.TarInfo(arc)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            tf.addfile(info, io.BytesIO(b''))
        for fn in files:
            path = os.path.join(root, fn)
            arc = os.path.relpath(path, 'data').replace('\\', '/')
            info = tf.gettarinfo(path, arc)
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            if 'init.d' in arc or 'acnexus_service.py' in arc or arc.endswith('.sh'):
                info.mode = 0o755
            with open(path, 'rb') as fh:
                tf.addfile(info, fh)

# Build gzip-tar IPK (compatible with OpenWRT 24.10)
out = '../acnexus_openwrt_v5.0.1_all.ipk'
with tarfile.open(out, 'w:gz', format=tarfile.USTAR_FORMAT) as tf:
    # Add as flat entries
    for name in ['debian-binary', 'control.tar.gz', 'data.tar.gz']:
        info = tarfile.TarInfo(name)
        info.size = os.path.getsize(name)
        info.uid = info.gid = 0
        info.uname = info.gname = 'root'
        with open(name, 'rb') as fh:
            tf.addfile(info, fh)

print(f'Done: {out} ({os.path.getsize(out)} bytes)')
