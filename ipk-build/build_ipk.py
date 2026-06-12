import tarfile, os, io, shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Step 0: 同步 data/ <- ../broadlinkac/files/（避免 stale data 打包旧代码）
src = '../broadlinkac/files'
dst = 'data'
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)

# 清理 __pycache__ 和 .pyc（不打包进 IPK）
for root, dirs, files in os.walk(dst):
    for d in list(dirs):
        if d == '__pycache__':
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            dirs.remove(d)
    for f in files:
        if f.endswith('.pyc'):
            os.remove(os.path.join(root, f))
print(f'Synced: {src} -> {dst}')

# Clean
for f in ['control.tar.gz', 'data.tar.gz', 'debian-binary']:
    if os.path.exists(f):
        os.remove(f)

# debian-binary
with open('debian-binary', 'w') as f:
    f.write('2.0\n')

# control.tar.gz — USTAR for OpenWRT busybox compatibility
with tarfile.open('control.tar.gz', 'w:gz', format=tarfile.USTAR_FORMAT) as tf:
    ti = tarfile.TarInfo('./control')
    ti.size = os.path.getsize('CONTROL/control')
    ti.mode = 0o644
    ti.uid = ti.gid = 0
    with open('CONTROL/control', 'rb') as f:
        tf.addfile(ti, f)

    ti2 = tarfile.TarInfo('./postinst')
    ti2.size = os.path.getsize('CONTROL/postinst')
    ti2.mode = 0o755
    ti2.uid = ti2.gid = 0
    with open('CONTROL/postinst', 'rb') as f:
        tf.addfile(ti2, f)

# data.tar.gz — USTAR for OpenWRT busybox compatibility
with tarfile.open('data.tar.gz', 'w:gz', format=tarfile.USTAR_FORMAT) as tf:
    for root, dirs, files in os.walk('data'):
        for d in dirs:
            path = os.path.join(root, d)
            arc = './' + os.path.relpath(path, 'data').replace('\\', '/') + '/'
            ti = tarfile.TarInfo(arc)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.uid = ti.gid = 0
            tf.addfile(ti, io.BytesIO(b''))
        for fn in files:
            path = os.path.join(root, fn)
            arc = './' + os.path.relpath(path, 'data').replace('\\', '/')
            ti = tarfile.TarInfo(arc)
            ti.size = os.path.getsize(path)
            ti.mode = 0o755 if ('init.d' in arc or fn == 'broadlinkac_service.py' or arc.endswith('.sh')) else 0o644
            ti.uid = ti.gid = 0
            with open(path, 'rb') as f:
                tf.addfile(ti, f)

# Build ar
def ar_pad(data):
    return data + b'\n' if len(data) % 2 else data

entries = [
    ('debian-binary', os.stat('debian-binary')),
    ('control.tar.gz', os.stat('control.tar.gz')),
    ('data.tar.gz', os.stat('data.tar.gz')),
]

result = b'!<arch>\n'
for name, st in entries:
    hdr = (
        name.ljust(16)[:16].encode() +
        str(int(st.st_mtime)).ljust(12)[:12].encode() +
        b'0     ' + b'0     ' +
        b'100644  ' +
        str(st.st_size).ljust(10)[:10].encode() +
        b'\x60\n'
    )
    assert len(hdr) == 60, f'header len={len(hdr)}'
    result += hdr
    with open(name, 'rb') as f:
        result += ar_pad(f.read())

out = '../broadlinkac_3.1-1_aarch64_generic.ipk'
with open(out, 'wb') as f:
    f.write(result)
print(f'Done: {out} ({len(result)} bytes)')
