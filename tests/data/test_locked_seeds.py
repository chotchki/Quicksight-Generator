"""X.1.k — locked-SQL byte check for the demo seed pipeline.

Each ``tests/data/_locked_seeds/<instance>.<dialect>.sql`` file is the
SHA256-stamped output that ``data apply`` would emit for the named
``(L2 instance, dialect)`` pair at the canonical anchor
``date(2030, 1, 1)``. This test re-emits and asserts byte-equality
against the locked file.

Auto-discovers files in the directory — adding a new (instance,
dialect) pair to the lock surface is "drop the file"; no Python
constant to maintain.

Refresh after a reviewed seed-shape change with
``quicksight-gen data lock -c <postgres-or-oracle config> --l2 <yaml>``
(once per dialect). The CLI keys off ``demo_database_url`` in the
config to pick which dialect's lock file to write.
"""

from __future__ import annotations

import difflib
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from quicksight_gen.cli._helpers import build_full_seed_sql
from quicksight_gen.common.l2 import load_instance
from quicksight_gen.common.sql.dialect import Dialect

from tests._test_helpers import make_test_config


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCKED_DIR = _REPO_ROOT / "tests" / "data" / "_locked_seeds"
_L2_DIR = _REPO_ROOT / "tests" / "l2"

# Same anchor as the CLI (X.1.k _CANONICAL_LOCK_ANCHOR). Drift this and
# every locked file becomes wrong; pin it here as a test invariant.
_CANONICAL_ANCHOR = date(2030, 1, 1)


def _discover_locked_files() -> list[pytest.ParameterSet]:
    if not _LOCKED_DIR.exists():
        return []
    out: list[pytest.ParameterSet] = []
    for p in sorted(_LOCKED_DIR.glob("*.sql")):
        # filename: <instance>.<dialect>.sql
        stem = p.stem  # "<instance>.<dialect>"
        if stem.count(".") != 1:
            raise RuntimeError(
                f"Locked seed file has unexpected name: {p.name!r}. "
                f"Expected `<instance>.<dialect>.sql`."
            )
        instance_name, dialect_name = stem.rsplit(".", 1)
        out.append(pytest.param(p, instance_name, dialect_name, id=stem))
    return out


_LOCKED_FILES = _discover_locked_files()


@pytest.mark.skipif(
    not _LOCKED_FILES,
    reason="no locked seed files found under tests/data/_locked_seeds/",
)
@pytest.mark.parametrize(
    "locked_path,instance_name,dialect_name", _LOCKED_FILES,
)
def test_locked_seed_matches_fresh_emit(
    locked_path: Path, instance_name: str, dialect_name: str,
) -> None:
    """Re-emit the seed for ``(instance, dialect)`` at the canonical
    anchor and assert it matches the locked file byte-for-byte.

    On drift, fail with a unified diff of the first ~50 changed lines
    so the reviewer sees the actual SQL shift, not just a hash flip.
    Re-lock with ``quicksight-gen data lock -c <config> --l2 <yaml>``.
    """
    yaml_path = _L2_DIR / f"{instance_name}.yaml"
    assert yaml_path.exists(), (
        f"Lock file {locked_path.name} references L2 instance "
        f"{instance_name!r} but {yaml_path} doesn't exist. "
        f"Either rename the lock file or restore the YAML."
    )
    instance = load_instance(yaml_path)
    cfg = make_test_config(
        dialect=Dialect(dialect_name),
    ).with_l2_instance_prefix(instance_name)
    fresh = build_full_seed_sql(cfg, instance, anchor=_CANONICAL_ANCHOR)

    on_disk = locked_path.read_text()
    if fresh == on_disk:
        return
    diff = list(difflib.unified_diff(
        on_disk.splitlines(keepends=True),
        fresh.splitlines(keepends=True),
        fromfile=f"locked/{locked_path.name}",
        tofile=f"fresh/{locked_path.name}",
        n=2,
    ))
    snippet = "".join(diff[:50])
    truncated = (
        f"\n... ({len(diff) - 50} more diff lines truncated)"
        if len(diff) > 50 else ""
    )
    pytest.fail(
        f"Locked seed drifted from fresh emit for "
        f"({instance_name!r}, {dialect_name!r}).\n"
        f"Re-lock with: quicksight-gen data lock -c <config.yaml> "
        f"--l2 tests/l2/{instance_name}.yaml\n\n"
        f"First 50 diff lines:\n{snippet}{truncated}"
    )


def test_lock_dir_only_holds_known_dialects() -> None:
    """Every file under ``_locked_seeds/`` must end ``.<dialect>.sql``
    for a real Dialect enum value. Catches typos like ``...postgress.sql``."""
    if not _LOCKED_DIR.exists():
        pytest.skip("lock dir not yet created")
    valid = {d.value for d in Dialect}
    for p in _LOCKED_DIR.glob("*.sql"):
        stem = p.stem
        assert stem.count(".") == 1, (
            f"Lock filename {p.name!r} should have exactly one dot "
            f"between instance and dialect."
        )
        _, dialect_name = stem.rsplit(".", 1)
        assert dialect_name in valid, (
            f"Lock filename {p.name!r} cites unknown dialect "
            f"{dialect_name!r}; valid: {sorted(valid)}"
        )
