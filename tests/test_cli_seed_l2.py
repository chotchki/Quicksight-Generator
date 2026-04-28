"""CLI smoke tests for ``quicksight-gen demo seed-l2`` (M.2d.6).

Three flows:
- Default: emit SQL to stdout (or `-o file`).
- ``--lock``: rewrite the YAML's ``seed_hash:`` field with the actual
  auto-seed SHA256.
- ``--check-hash``: exit 0 when YAML's ``seed_hash`` matches, exit 1
  on mismatch.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main


SPEC_YAML = Path(__file__).parent / "l2" / "spec_example.yaml"


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Path:
    """A writable copy of spec_example.yaml — the lock test needs to
    mutate the file without touching the committed fixture."""
    dst = tmp_path / "instance.yaml"
    shutil.copy(SPEC_YAML, dst)
    return dst


def test_seed_l2_emits_sql_to_stdout(tmp_yaml: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "seed-l2", str(tmp_yaml)])
    assert result.exit_code == 0, result.output
    assert "INSERT INTO spec_example_transactions" in result.output
    assert "INSERT INTO spec_example_daily_balances" in result.output


def test_seed_l2_writes_to_file(tmp_yaml: Path, tmp_path: Path) -> None:
    out = tmp_path / "seed.sql"
    runner = CliRunner()
    result = runner.invoke(
        main, ["demo", "seed-l2", str(tmp_yaml), "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    sql = out.read_text()
    assert "INSERT INTO spec_example_transactions" in sql


def test_seed_l2_lock_writes_hash_into_yaml(
    tmp_yaml: Path, tmp_path: Path,
) -> None:
    """`--lock` writes the actual SHA256 into the YAML's seed_hash field."""
    # Replace the existing seed_hash with a wrong-but-valid-shape hex
    # value first to prove --lock rewrites (not appends). Mixing in
    # alphabetic chars dodges YAML's "all-digit string parses as int"
    # quirk that would trip the loader's `must be a string` check.
    wrong = "deadbeef" * 8
    text = tmp_yaml.read_text()
    text = text.replace(
        "seed_hash: d980d31ca2ca7a4d692c836220ab5d0a7a0a771d4c789611fb5992cdb7251965",
        f"seed_hash: {wrong}",
    )
    tmp_yaml.write_text(text)

    out = tmp_path / "out.sql"
    runner = CliRunner()
    result = runner.invoke(
        main, ["demo", "seed-l2", str(tmp_yaml), "--lock", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output

    # The YAML's seed_hash should now match what emit_seed produced.
    new_text = tmp_yaml.read_text()
    assert "deadbeef" not in new_text  # the wrong-value placeholder is gone
    # Pull the actual hash from the rewritten file.
    import re
    m = re.search(r"^seed_hash:\s+([0-9a-f]{64})\s*$", new_text, re.MULTILINE)
    assert m is not None
    written_hash = m.group(1)
    # And it should match the SHA256 of the SQL the CLI wrote to disk.
    sql = out.read_text()
    expected = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert written_hash == expected


def test_seed_l2_lock_appends_when_field_missing(tmp_path: Path) -> None:
    """`--lock` on a YAML without seed_hash appends the field."""
    minimal = tmp_path / "no_hash.yaml"
    minimal.write_text(
        "instance: lock_test\n"
        "accounts:\n"
        "  - id: control\n"
        "    role: ControlAccount\n"
        "    scope: internal\n"
        "    expected_eod_balance: 0\n"
        "  - id: ext\n"
        "    role: ExternalParty\n"
        "    scope: external\n"
        "account_templates:\n"
        "  - role: CustomerSub\n"
        "    scope: internal\n"
        "    parent_role: ControlAccount\n"
        "rails:\n"
        "  - name: Inbound\n"
        "    transfer_type: ach\n"
        "    source_role: ExternalParty\n"
        "    destination_role: CustomerSub\n"
        "    expected_net: 0\n"
        "    source_origin: ExternalForcePosted\n"
        "    destination_origin: InternalInitiated\n"
    )
    assert "seed_hash" not in minimal.read_text()

    runner = CliRunner()
    result = runner.invoke(main, ["demo", "seed-l2", str(minimal), "--lock"])
    assert result.exit_code == 0, result.output

    text = minimal.read_text()
    import re
    assert re.search(r"^seed_hash:\s+[0-9a-f]{64}\s*$", text, re.MULTILINE)


def test_seed_l2_check_hash_passes_when_matching(tmp_yaml: Path) -> None:
    """`--check-hash` exits 0 when YAML's seed_hash matches actual."""
    runner = CliRunner()
    result = runner.invoke(
        main, ["demo", "seed-l2", str(tmp_yaml), "--check-hash"],
    )
    assert result.exit_code == 0, result.output
    assert "[ok] seed_hash matches" in result.output


def test_seed_l2_check_hash_fails_on_drift(tmp_yaml: Path) -> None:
    """`--check-hash` exits 1 when YAML's seed_hash doesn't match actual."""
    text = tmp_yaml.read_text()
    text = text.replace(
        "seed_hash: d980d31ca2ca7a4d692c836220ab5d0a7a0a771d4c789611fb5992cdb7251965",
        "seed_hash: " + ("a" * 64),
    )
    tmp_yaml.write_text(text)

    runner = CliRunner()
    result = runner.invoke(
        main, ["demo", "seed-l2", str(tmp_yaml), "--check-hash"],
    )
    assert result.exit_code == 1
    assert "seed_hash mismatch" in result.output


def test_seed_l2_check_hash_fails_when_field_absent(tmp_path: Path) -> None:
    """`--check-hash` on a YAML lacking seed_hash explains how to lock it."""
    minimal = tmp_path / "no_hash.yaml"
    minimal.write_text(
        "instance: no_hash_yet\n"
        "accounts:\n"
        "  - id: only\n"
        "    role: Only\n"
        "    scope: internal\n"
    )
    runner = CliRunner()
    result = runner.invoke(
        main, ["demo", "seed-l2", str(minimal), "--check-hash"],
    )
    assert result.exit_code == 1
    assert "no `seed_hash:` field" in result.output


def test_seed_l2_logs_omitted_plant_kinds(tmp_path: Path) -> None:
    """When the L2 lacks structures for some plants, the CLI logs them
    as warnings but still emits SQL."""
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text(
        "instance: warn_test\n"
        "accounts:\n"
        "  - id: control\n"
        "    role: ControlAccount\n"
        "    scope: internal\n"
        "  - id: ext\n"
        "    role: ExternalParty\n"
        "    scope: external\n"
        "account_templates:\n"
        "  - role: CustomerSub\n"
        "    scope: internal\n"
        "    parent_role: ControlAccount\n"
        "rails:\n"
        "  - name: Inbound\n"
        "    transfer_type: ach\n"
        "    source_role: ExternalParty\n"
        "    destination_role: CustomerSub\n"
        "    expected_net: 0\n"
        "    source_origin: ExternalForcePosted\n"
        "    destination_origin: InternalInitiated\n"
    )
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "seed-l2", str(minimal)])
    assert result.exit_code == 0, result.output
    # Warnings go to stderr, which Click's CliRunner captures separately;
    # by default both streams concatenate into result.output.
    assert "[warn] omitted LimitBreachPlant" in result.output
    assert "[warn] omitted StuckPendingPlant" in result.output
    assert "[warn] omitted StuckUnbundledPlant" in result.output
