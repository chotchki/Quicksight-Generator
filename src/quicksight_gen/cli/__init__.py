"""``quicksight-gen`` CLI — Q.3.a v8.0.0 redesign in progress.

The old monolithic cli.py has been renamed to cli_legacy.py during
the Q.3.a transition. The legacy ``main`` group is still the live
entry point until the new artifact groups (schema | data | json |
docs) reach parity. As each new group lands here, it gets registered
on the legacy ``main`` so the old + new commands coexist; once all
four artifact groups are in place, the old top-level verbs get
dropped in one atomic commit (Q.3.a.5 finalize).

Final shape:

  schema apply | clean | test
  data apply | refresh | clean | test
  json apply | clean | test | probe
  docs apply | serve | clean | test | export | screenshot

Per-artifact files: schema.py, data.py, json.py, docs.py.
Shared helpers: _helpers.py.
"""

from __future__ import annotations

# Re-export the live entry point so the existing console script
# (``quicksight-gen = "quicksight_gen.cli:main"``) keeps resolving.
# The legacy module carries every old-shape command (generate /
# deploy / cleanup / demo / export / probe) plus the Q.3.a.1+2
# piecewise demo emit-* / apply-* shipped in v7.4.0.
from quicksight_gen.cli_legacy import (  # noqa: F401 — re-exported
    APP_CHOICE,
    APPS,
    DEMO_APP_CHOICE,
    _SCREENSHOT_APPS,
    _parse_viewport,
    main,
)

# Register the new artifact groups onto the legacy main as they land.
# Each `main.add_command(...)` line gives the integrator the new
# verb without removing the old one, so we can ship one artifact
# group at a time and verify before atomically dropping the old verbs.
from quicksight_gen.cli.schema import schema as _schema_group

main.add_command(_schema_group, name="schema")


__all__ = ["main"]
