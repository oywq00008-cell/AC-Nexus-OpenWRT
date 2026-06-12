import hashlib, os

base = "/Users/oc/workspace/BroadlinkAC-OpenWRT"

def get_files(root_dir):
    files = set()
    for root, dirs, fnames in os.walk(root_dir):
        for f in fnames:
            rel = os.path.relpath(os.path.join(root, f), root_dir)
            files.add(rel)
    return files

ipk_files = get_files(os.path.join(base, "ipk-build", "data"))
bc_files = get_files(os.path.join(base, "broadlinkac", "files"))

print(f"ipk-build/data/:       {len(ipk_files)} files")
print(f"broadlinkac/files/:    {len(bc_files)} files")

only_ipk = sorted(ipk_files - bc_files)
only_bc = sorted(bc_files - ipk_files)
common = sorted(ipk_files & bc_files)

if only_ipk:
    print(f"\nOnly in ipk-build/data/ ({len(only_ipk)}):")
    for f in only_ipk: print(f"  {f}")
if only_bc:
    print(f"\nOnly in broadlinkac/files/ ({len(only_bc)}):")
    for f in only_bc: print(f"  {f}")

if not only_ipk and not only_bc:
    print("File sets are identical (same structure)")

diff_files = []
for rel in common:
    p1 = os.path.join(base, "ipk-build", "data", rel)
    p2 = os.path.join(base, "broadlinkac", "files", rel)
    with open(p1, "rb") as f: h1 = hashlib.md5(f.read()).hexdigest()
    with open(p2, "rb") as f: h2 = hashlib.md5(f.read()).hexdigest()
    if h1 != h2:
        diff_files.append(rel)

if diff_files:
    print(f"\nContent differs ({len(diff_files)}):")
    for f in diff_files: print(f"  ! {f}")
else:
    print("All common files have identical content (MD5 match)")

print(f"\n=== VERDICT ===")
if not only_ipk and not only_bc and not diff_files:
    print("RESULT: 完全重复（结构+内容均一致）")
elif not only_ipk and not only_bc and diff_files:
    print("RESULT: 目录结构相同，但部分文件内容有差异")
else:
    print("RESULT: 不完全相同")
