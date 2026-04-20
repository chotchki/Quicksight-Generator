#!/usr/bin/env python3
"""Bake a sample `out/` bundle for the GitHub Release page.

Runs `quicksight-gen generate --all` against `examples/config.yaml` and zips
the resulting JSON tree to `dist/out-sample.zip`. Evaluators can download the
zip from a GitHub Release and inspect every generated theme / analysis /
dashboard / dataset definition without installing the tool.

Usage:
    python scripts/bake_sample_output.py
    python scripts/bake_sample_output.py --config examples/config.yaml \\
                                         --output dist/out-sample.zip
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "examples" / "config.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "out-sample.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", "-c",
        type=Path, default=DEFAULT_CONFIG,
        help=f"Path to config YAML (default: {DEFAULT_CONFIG.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path, default=DEFAULT_OUTPUT,
        help=f"Path to write the zip (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="qs-bake-") as tmpdir:
        out_dir = Path(tmpdir) / "out"
        cmd = [
            sys.executable, "-m", "quicksight_gen", "generate", "--all",
            "-c", str(args.config),
            "-o", str(out_dir),
        ]
        print(f"running: {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"error: generate failed (exit {result.returncode})", file=sys.stderr)
            return result.returncode

        files = sorted(out_dir.rglob("*.json"))
        if not files:
            print("error: generate produced no JSON files", file=sys.stderr)
            return 1

        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            args.output.unlink()
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, arcname=f.relative_to(out_dir.parent))

        size_kb = args.output.stat().st_size / 1024
        print(f"wrote {args.output} ({len(files)} files, {size_kb:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
