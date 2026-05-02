"""``quicksight-gen`` CLI — four artifact groups (Q.3.a, v8.0.0).

The CLI is organized around the four artifacts the tool produces:

  schema  apply | clean | test
  data    apply | refresh | clean | hash | etl-example | test
  json    apply | clean | test | probe
  docs    apply | serve | clean | test | export | screenshot

Every artifact's ``apply``/``clean`` defaults to *emit* (print SQL to
stdout, write JSON to ``out/``, build site to ``site/``). Pass
``--execute`` to actually run the destructive thing (connect to the
DB, deploy to AWS). The ``docs`` group has no ``--execute`` because
building a static site is the operation.

Per-artifact files: ``schema.py``, ``data.py``, ``json.py``,
``docs.py``. Shared helpers: ``_helpers.py``. Per-app JSON-emit
helpers: ``_app_builders.py``.
"""

from __future__ import annotations

import click

from quicksight_gen import __version__
from quicksight_gen.cli.data import data as _data_group
from quicksight_gen.cli.docs import docs as _docs_group
from quicksight_gen.cli.json import json_ as _json_group
from quicksight_gen.cli.schema import schema as _schema_group


@click.group()
@click.version_option(version=__version__, prog_name="quicksight-gen")
def main() -> None:
    """Generate + deploy AWS QuickSight dashboards from one L2 YAML."""


main.add_command(_schema_group, name="schema")
main.add_command(_data_group, name="data")
main.add_command(_json_group, name="json")
main.add_command(_docs_group, name="docs")


__all__ = ["main"]
