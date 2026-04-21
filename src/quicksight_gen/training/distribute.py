#!/usr/bin/env python3
"""Package the handbook, publisher, and mapping template as a
whitelabel training-kit zip.

Meant to be run from inside `training/`. Each consumer fills in
their own mapping.yaml locally and runs publish.py against it.

The distribution bundles:
  - handbook/                     SNB-codenamed training material
  - publish.py                    string-substitution publisher
  - mapping.yaml.example          template of strings needing subs
  - QUICKSTART.md                 recipient-facing usage notes

Stdlib-only; no pip install required.

Usage:
    ./distribute.py              # write ./dist/handbook-whitelabel-YYYY-MM-DD.zip
    ./distribute.py --dry-run    # list what would be packaged
    ./distribute.py --version 1.0.0
"""

import argparse
import datetime
import os
import sys
import zipfile


FILES = ["QUICKSTART.md", "publish.py", "mapping.yaml.example"]
DIRS  = ["handbook"]


def iter_entries(source_root, prefix):
    """Yield (arcname, src_path) for everything in the kit."""
    for rel in FILES:
        src = os.path.join(source_root, rel)
        if not os.path.isfile(src):
            sys.exit(f"Missing expected file: {src}")
        yield (f"{prefix}/{rel}", src)

    for d in DIRS:
        src_dir = os.path.join(source_root, d)
        if not os.path.isdir(src_dir):
            sys.exit(f"Missing expected directory: {src_dir}")
        for root, dirnames, files in os.walk(src_dir):
            # Skip hidden dirs (e.g. .git, .DS_Store leftovers).
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, source_root)
                yield (f"{prefix}/{rel}", src)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="List what would be packaged; write nothing")
    ap.add_argument("--name", default="handbook-whitelabel",
                    help="Base name of the zip / top-level folder "
                         "(default: handbook-whitelabel)")
    ap.add_argument("--version",
                    default=datetime.date.today().isoformat(),
                    help="Version tag in the filename "
                         "(default: today's date, YYYY-MM-DD)")
    ap.add_argument("--output-dir", default="./dist",
                    help="Directory to write the zip into "
                         "(default: ./dist)")
    args = ap.parse_args()

    prefix = args.name
    filename = f"{args.name}-{args.version}.zip"
    out_path = os.path.join(args.output_dir, filename)

    entries = list(iter_entries(".", prefix))

    if args.dry_run:
        for arc, _ in entries:
            print(arc)
        print()
        print(f"{len(entries)} entries would be packaged.")
        print(f"Would write: {out_path}")
        return

    os.makedirs(args.output_dir, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in entries:
            zf.write(src, arcname)

    size = os.path.getsize(out_path)
    print(f"Wrote {out_path} ({len(entries)} entries, {size:,} bytes)")


if __name__ == "__main__":
    main()
