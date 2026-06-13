import tarfile
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Write debian-binary
with open('debian-binary', 'w') as f:
    f.write('2.0\n')

# Create control.tar.gz
with tarfile.open('control.tar.gz', 'w:gz') as tf:
    for path in ['CONTROL/control', 'CONTROL/postinst']:
        tf.add(path)

# Create data.tar.gz  
with tarfile.open('data.tar.gz', 'w:gz') as tf:
    for item in sorted(os.listdir('data')):
        tf.add(f'data/{item}', item)

# Create ar archive (.ipk)
files = ['debian-binary', 'control.tar.gz', 'data.tar.gz']
ipk_path = '../broadlinkac_3.2-1_aarch64_cortex-a53.ipk'
with open(ipk_path, 'wb') as ar:
    ar.write(b'!<arch>\n')
    for fname in files:
        size = os.path.getsize(fname)
        name = fname.ljust(16)[:16]
        mtime = '0'.ljust(12)
        header = f'{name}{mtime}0     0     100644  {size}`\n'
        ar.write(header.encode())
        with open(fname, 'rb') as f:
            data = f.read()
            ar.write(data)
            if len(data) % 2:
                ar.write(b'\n')

size_kb = os.path.getsize(ipk_path) / 1024
print(f'Done: {ipk_path} ({size_kb:.0f} KB)')
