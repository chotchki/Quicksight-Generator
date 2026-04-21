"""Tests for `quicksight-gen export` (docs + training)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main
from quicksight_gen.whitelabel import apply_whitelabel, parse_mapping


def test_bundled_docs_directory_exists():
    docs = files("quicksight_gen") / "docs"
    assert docs.is_dir()
    assert (docs / "index.md").is_file()
    assert (docs / "Schema_v3.md").is_file()
    assert (docs / "handbook" / "customization.md").is_file()


def test_bundled_training_directory_exists():
    training = files("quicksight_gen") / "training"
    assert training.is_dir()
    assert (training / "handbook" / "README.md").is_file()
    assert (training / "mapping.yaml.example").is_file()


def test_export_docs_writes_tree(tmp_path: Path):
    runner = CliRunner()
    out = tmp_path / "exported-docs"
    result = runner.invoke(main, ["export", "docs", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "index.md").is_file()
    assert (out / "Schema_v3.md").is_file()
    assert (out / "handbook" / "customization.md").is_file()
    assert (out / "walkthroughs" / "customization" /
            "how-do-i-test-my-customization.md").is_file()


def test_export_docs_requires_output(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["export", "docs"])
    assert result.exit_code != 0
    assert "--output" in result.output or "Missing option" in result.output


def test_export_training_no_mapping_ships_canonical(tmp_path: Path):
    runner = CliRunner()
    out = tmp_path / "training"
    result = runner.invoke(main, ["export", "training", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "README.md").is_file()
    # Canonical names should still be present without a mapping.
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "Sasquatch" in readme or "SNB" in readme


def test_export_training_with_mapping_substitutes(tmp_path: Path):
    runner = CliRunner()
    mapping_path = tmp_path / "mapping.yaml"
    mapping_path.write_text(
        '"Sasquatch National Bank": "Acme Bank"\n'
        '"SNB": "ACME"\n'
        '"Bigfoot Brews": "Latte Lounge"\n',
        encoding="utf-8",
    )
    out = tmp_path / "training-wl"
    result = runner.invoke(
        main,
        ["export", "training", "-o", str(out), "--mapping", str(mapping_path)],
    )
    assert result.exit_code == 0, result.output

    # At least one file must have been substituted.
    rewritten = list(out.rglob("*.md"))
    assert rewritten
    combined = "\n".join(p.read_text(encoding="utf-8") for p in rewritten)
    # Canonical strings replaced wholesale.
    assert "Sasquatch National Bank" not in combined
    assert "Bigfoot Brews" not in combined
    # New brand present in at least one file.
    assert "Acme Bank" in combined or "ACME" in combined


def test_export_training_dry_run_writes_nothing(tmp_path: Path):
    runner = CliRunner()
    out = tmp_path / "training-dry"
    result = runner.invoke(
        main, ["export", "training", "-o", str(out), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert not out.exists()


def test_parse_mapping_supports_quoted_and_bare_keys(tmp_path: Path):
    mapping_path = tmp_path / "m.yaml"
    mapping_path.write_text(
        '# comment\n'
        'institution:\n'
        '  "Sasquatch National Bank": "Acme Bank"\n'
        '  SNB: ACME\n'
        '  empty_skip: \n'
        'merchants:\n'
        '  "Bigfoot Brews": "Latte Lounge"  # trailing comment\n',
        encoding="utf-8",
    )
    subs = parse_mapping(mapping_path)
    assert subs == {
        "Sasquatch National Bank": "Acme Bank",
        "SNB": "ACME",
        "Bigfoot Brews": "Latte Lounge",
    }


def test_apply_whitelabel_longest_first_ordering(tmp_path: Path):
    """SNB inside 'Sasquatch National Bank' must not be rewritten first."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.md").write_text("Sasquatch National Bank (SNB)", encoding="utf-8")
    out = tmp_path / "out"
    result = apply_whitelabel(
        src, out,
        {"SNB": "ACME", "Sasquatch National Bank": "Acme Bank"},
    )
    assert result.total_substitutions == 2
    assert (out / "f.md").read_text(encoding="utf-8") == "Acme Bank (ACME)"


def test_apply_whitelabel_flags_leftover_canonical_strings(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.md").write_text("Bigfoot Brews shipped", encoding="utf-8")
    out = tmp_path / "out"
    result = apply_whitelabel(src, out, {"Bigfoot Brews": "Latte Lounge"})
    assert not result.leftovers  # rewritten cleanly

    (src / "g.md").write_text("Cascade Timber Mill remains", encoding="utf-8")
    out2 = tmp_path / "out2"
    result = apply_whitelabel(src, out2, {"Bigfoot Brews": "Latte Lounge"})
    assert any("g.md" in rel for rel, _ in result.leftovers)


def test_apply_whitelabel_missing_source_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        apply_whitelabel(tmp_path / "nope", tmp_path / "out", {})
