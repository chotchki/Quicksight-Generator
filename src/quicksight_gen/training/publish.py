#!/usr/bin/env python3
"""Publish the SNB-named handbook as a real-program-flavored copy.

Reads a YAML-ish mapping file of 'old: new' substitution pairs, walks
the handbook/ tree, and emits a substituted copy to an output directory
ready to upload to the GitLab wiki.

The mapping file supports a small subset of YAML:
  - Nested group headers (e.g. `institution:`) are ignored
  - Leaf lines are `key: value` or `"key with spaces": "value"`
  - Comments start with `#` and run to end of line
  - Empty values are skipped (so unfilled template entries are no-ops)

Stdlib-only; no pip install required.

Usage:
    ./publish.py [-n] [--mapping MAPPING] [--source SOURCE] [--output OUTPUT]
    ./publish.py --dry-run
"""

import argparse
import os
import re
import shutil
import sys


LEAF_RE = re.compile(r'^\s*(?:"([^"]+)"|([^:\s][^:]*?))\s*:\s*(.*?)\s*$')

CHECK_PATTERNS = [
    r"Sasquatch", r"\bSNB\b", r"Bigfoot", r"Big Meadow",
    r"Cascade Timber", r"Pinecrest", r"Harvest Moon",
]


def parse_mapping(path):
    subs = {}
    with open(path) as fp:
        for line in fp:
            raw = line.rstrip("\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            idx = raw.find(" #")
            if idx >= 0:
                raw = raw[:idx]
            m = LEAF_RE.match(raw)
            if not m:
                continue
            key = m.group(1) or m.group(2)
            val = m.group(3).strip()
            if not val:
                continue
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if not val:
                continue
            subs[key] = val
    return subs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mapping", default="./mapping.yaml",
                    help="YAML-subset mapping file (default: ./mapping.yaml)")
    ap.add_argument("--source", default="./handbook",
                    help="Source directory to publish (default: ./handbook)")
    ap.add_argument("--output", default="./.publish",
                    help="Output directory (default: ./.publish)")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="Report what would happen; write nothing")
    args = ap.parse_args()

    if not os.path.isfile(args.mapping):
        sys.exit(f"Mapping file not found: {args.mapping}")
    if not os.path.isdir(args.source):
        sys.exit(f"Source dir not found: {args.source}")

    subs = parse_mapping(args.mapping)
    if not subs:
        print(f"WARNING: No non-empty substitutions in {args.mapping}; "
              f"output will match source verbatim.")

    # Longest-key-first avoids "SNB" substituting inside a partially-
    # rewritten "Sasquatch National Bank" that hadn't yet been processed.
    ordered_keys = sorted(subs.keys(), key=len, reverse=True)
    print(f"Loaded {len(subs)} substitutions from {args.mapping}.")

    if not args.dry_run:
        if os.path.isdir(args.output):
            shutil.rmtree(args.output)
        os.makedirs(args.output, exist_ok=True)

    produced = []  # list of (rel, content, file_subs)
    for root, _, files in os.walk(args.source):
        for fname in sorted(files):
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, args.source)
            with open(src) as fp:
                content = fp.read()
            file_subs = 0
            for key in ordered_keys:
                hits = content.count(key)
                if hits:
                    content = content.replace(key, subs[key])
                    file_subs += hits
            produced.append((rel, content, file_subs))

    total_subs = sum(s for _, _, s in produced)

    for rel, content, file_subs in produced:
        if args.dry_run:
            print(f"DRY-RUN  {rel}  ({file_subs} subs)")
        else:
            dst = os.path.join(args.output, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w") as fp:
                fp.write(content)
            print(f"WROTE    {rel}  ({file_subs} subs)")

    print()
    print(f"Done. {len(produced)} files processed, "
          f"~{total_subs} substitutions applied.")

    leftovers = []
    for rel, content, _ in produced:
        for pat in CHECK_PATTERNS:
            if re.search(pat, content):
                leftovers.append((rel, pat))
                break

    if leftovers:
        print("\nWARNING: Possible untranslated SNB strings remain after substitution:")
        for f, pat in leftovers:
            print(f"  {f}  matches {pat}")
        print("Update the mapping and re-run, or accept if intentional.")


if __name__ == "__main__":
    main()
