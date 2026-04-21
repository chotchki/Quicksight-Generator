"""Substitute branding strings across a directory tree.

Used by ``quicksight-gen export training`` to produce a real-program-flavored
copy of the bundled Sasquatch-named training handbook. The mapping format is
a small subset of YAML (no external dependency); see
``training/mapping.yaml.example`` shipped in the wheel for the template.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


_LEAF_RE = re.compile(r'^\s*(?:"([^"]+)"|([^:\s][^:]*?))\s*:\s*(.*?)\s*$')

_LEFTOVER_PATTERNS = [
    r"Sasquatch", r"\bSNB\b", r"Bigfoot", r"Big Meadow",
    r"Cascade Timber", r"Pinecrest", r"Harvest Moon",
]


@dataclass
class WhitelabelResult:
    files_processed: int = 0
    total_substitutions: int = 0
    leftovers: list[tuple[str, str]] = field(default_factory=list)
    per_file: list[tuple[str, int]] = field(default_factory=list)


def parse_mapping(path: Path) -> dict[str, str]:
    """Parse the YAML-subset mapping file.

    Supported syntax: ``key: value`` or ``"key with spaces": "value"`` per
    line; ``#`` comments; nested group headers are ignored; empty values
    are skipped.
    """
    subs: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw = raw_line.rstrip("\n")
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        idx = raw.find(" #")
        if idx >= 0:
            raw = raw[:idx]
        m = _LEAF_RE.match(raw)
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


def apply_whitelabel(
    source: Path,
    output: Path,
    mapping: dict[str, str] | None = None,
    *,
    dry_run: bool = False,
) -> WhitelabelResult:
    """Copy ``source`` to ``output`` applying string substitutions.

    Longest keys substitute first so prefixes (e.g. ``SNB`` inside
    ``Sasquatch National Bank``) don't get rewritten in the wrong order.
    Returns counts plus a list of files where canonical SNB-pattern strings
    survived the rewrite (suggests a missing mapping entry).
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    subs = mapping or {}
    ordered_keys = sorted(subs.keys(), key=len, reverse=True)
    result = WhitelabelResult()

    if not dry_run:
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

    for src_file in sorted(source.rglob("*")):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(source)
        try:
            content = src_file.read_text(encoding="utf-8")
            is_text = True
        except UnicodeDecodeError:
            content = ""
            is_text = False

        file_subs = 0
        if is_text:
            for key in ordered_keys:
                hits = content.count(key)
                if hits:
                    content = content.replace(key, subs[key])
                    file_subs += hits

        result.files_processed += 1
        result.total_substitutions += file_subs
        result.per_file.append((str(rel), file_subs))

        if not dry_run:
            dst = output / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if is_text:
                dst.write_text(content, encoding="utf-8")
            else:
                shutil.copy2(src_file, dst)

        if is_text:
            for pat in _LEFTOVER_PATTERNS:
                if re.search(pat, content):
                    result.leftovers.append((str(rel), pat))
                    break

    return result
