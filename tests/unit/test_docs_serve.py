"""X.2.s.1 regression — ``recon-gen docs serve`` must run mkdocs
with cwd set to the bundled ``mkdocs.yml``'s directory.

mkdocs-macros resolves its ``include_dir: docs/_macros`` against the
*process cwd*, not against the config file's directory (confirmed
empirically — same reason ``docs apply`` already sets cwd). From a
non-editable ``pip install`` the default cwd has no ``docs/_macros``,
so without the cwd override ``docs serve`` dies with
"docs/_macros does not exist" before it can serve a single page.

This is a wire-shape check (the `cwd=` kwarg); the CI
``docs-portable-install`` job exercises the real non-editable-wheel
path end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from recon_gen.cli import main as cli_root
from recon_gen.cli.docs import _BUNDLED_MKDOCS_YML


def test_docs_serve_runs_mkdocs_with_bundled_config_cwd() -> None:
    runner = CliRunner()
    with mock.patch(
        "recon_gen.cli.docs.subprocess.call", return_value=0,
    ) as m:
        result = runner.invoke(cli_root, ["docs", "serve", "-p", "9999"])
    assert result.exit_code == 0, result.output
    m.assert_called_once()
    _args, kwargs = m.call_args
    assert kwargs.get("cwd") == _BUNDLED_MKDOCS_YML.parent, (
        f"docs serve must run mkdocs with cwd={_BUNDLED_MKDOCS_YML.parent} "
        f"(so mkdocs-macros's include_dir: docs/_macros resolves) — got "
        f"cwd={kwargs.get('cwd')!r}"
    )
    # Sanity: the bundled config dir actually contains the macros tree
    # the override exists to make resolvable.
    assert (Path(_BUNDLED_MKDOCS_YML.parent) / "docs" / "_macros").is_dir()
