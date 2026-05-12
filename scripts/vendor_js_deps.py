#!/usr/bin/env python3
"""Vendor App 2's third-party browser libs from their CDNs (X.2.p).

App 2 ships a handful of pre-built minified JS/CSS dist files
(htmx / d3 / d3-sankey / tom-select / flatpickr / nouislider) committed
under ``src/quicksight_gen/common/html/assets/vendor/`` so a
``pip install quicksight-gen[serve]`` works offline (no CDN at runtime).
This script is the maintainer chore that keeps those committed files in
sync with ``vendor.lock`` — it is NOT a ``quicksight-gen`` CLI verb;
end users never run it.

Usage::

    python scripts/vendor_js_deps.py            # verify (CI mode) — assert
                                                # every committed file's
                                                # sha256 matches the lock
    python scripts/vendor_js_deps.py --update   # re-download each dep,
                                                # write the file, fill in
                                                # the sha256 in vendor.lock

To bump a version: edit ``vendor.lock``'s ``version`` + ``source_url`` for
the dep (set its ``sha256`` to ``null``), run ``--update``, commit the
changed file + lock + the ``render.py`` constant if the path changed.

Stdlib only (urllib + hashlib + json) — no third-party deps; runnable
from a bare ``python3``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

_VENDOR_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "quicksight_gen" / "common" / "html" / "assets" / "vendor"
)
_LOCK_PATH = _VENDOR_DIR / "vendor.lock"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_lock() -> dict[str, object]:
    return json.loads(_LOCK_PATH.read_text(encoding="utf-8"))


def _write_lock(lock: dict[str, object]) -> None:
    _LOCK_PATH.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _download(url: str) -> bytes:
    # CDN dist files; the sha256 in the lock is the integrity check.
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 — pinned https CDN URLs from vendor.lock, sha256-verified after
        return resp.read()


def cmd_verify(lock: dict[str, object]) -> int:
    deps: list[dict[str, str]] = lock["deps"]  # type: ignore[assignment]
    failures: list[str] = []
    for dep in deps:
        dest = _VENDOR_DIR / dep["dest"]
        expected = dep.get("sha256")
        if not expected:
            failures.append(
                f"{dep['name']}: vendor.lock has no sha256 — run "
                f"`python scripts/vendor_js_deps.py --update`"
            )
            continue
        if not dest.is_file():
            failures.append(
                f"{dep['name']}: missing vendored file {dep['dest']!r} — run "
                f"`python scripts/vendor_js_deps.py --update`"
            )
            continue
        actual = _sha256(dest.read_bytes())
        if actual != expected:
            failures.append(
                f"{dep['name']}: {dep['dest']!r} sha256 {actual} != "
                f"locked {expected} — re-run `--update` (and commit) if the "
                f"version bump is intentional"
            )
    if failures:
        print("vendor_js_deps: verification FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"vendor_js_deps: {len(deps)} vendored files OK (sha256 match)")
    return 0


def cmd_update(lock: dict[str, object]) -> int:
    deps: list[dict[str, str]] = lock["deps"]  # type: ignore[assignment]
    for dep in deps:
        dest = _VENDOR_DIR / dep["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {dep['name']} {dep['version']} <- {dep['source_url']}")
        data = _download(dep["source_url"])
        dest.write_bytes(data)
        dep["sha256"] = _sha256(data)
        print(f"    -> {dep['dest']}  ({len(data)} bytes, sha256 {dep['sha256'][:12]}…)")
    _write_lock(lock)
    print(f"vendor_js_deps: updated {len(deps)} files + vendor.lock")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true",
        help="Re-download each dep, write the file, fill in vendor.lock's sha256.",
    )
    args = parser.parse_args(argv)
    lock = _load_lock()
    return cmd_update(lock) if args.update else cmd_verify(lock)


if __name__ == "__main__":
    raise SystemExit(main())
