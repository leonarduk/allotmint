from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent.parent
src = root / 'backend' / 'tests'
dst = root / 'tests' / 'backend'

if not src.exists():
    print(f"Source {src} does not exist", file=sys.stderr)
    sys.exit(1)

if dst.exists():
    print(f"Destination {dst} already exists; files will be overwritten if names clash")
else:
    dst.mkdir(parents=True)

copied = []
for p in src.rglob('*'):
    rel = p.relative_to(src)
    target = dst / rel
    if p.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        copied.append(str(rel))

print(f"Copied {len(copied)} files from {src} to {dst}")
for c in copied:
    print(c)

