"""Dashboard-deploy helpers for the M.4.1 end-to-end harness (M.4.1.c).

Three surfaces:

1. ``generate_apps(cfg, l2_instance, out_dir)`` — write the JSON files
   the existing ``common.deploy.deploy()`` consumes: theme.json,
   per-dataset JSON under ``datasets/``, and per-app analysis +
   dashboard JSON. Mirrors what ``cli.py::_generate_l1_dashboard`` +
   ``_generate_l2_flow_tracing`` do but without the click I/O surface
   (so harness fixtures can call it directly).

2. ``extract_dashboard_ids(out_dir) -> dict[app_name, dashboard_id]``
   — reads the per-app -dashboard.json files and pulls each
   ``DashboardId``. The existing ``common.deploy.deploy()`` returns 0
   or 1 for success/failure, not the IDs themselves; reading the
   JSON files (the same ones deploy just sent to QS) is the cheapest
   way to recover the IDs without monkeypatching.

3. ``build_embed_urls(*, aws_account_id, aws_region, dashboard_ids,
   user_arn=None) -> dict[app_name, embed_url]`` — wraps
   ``common.browser.helpers.generate_dashboard_embed_url`` for each
   dashboard. Embed URLs MUST be signed by a client created in the
   dashboard region; the helper builds it internally from
   ``aws_region`` (M.4.1.i type-tightening — earlier signature took
   a pre-built client which made it possible to pass the wrong
   region's client and surface the cryptic "We can't open that
   dashboard, another Quick account or it was deleted" page).
   Single-use URLs → caller must be fixture-scoped to the test,
   not session.

Why this is its own module instead of inline-in-the-harness: the
JSON-writing logic + dashboard-id extraction are both unit-testable
without spinning up boto3 or QuickSight. The actual deploy step
delegates to ``common.deploy.deploy()`` (which already has the
delete-then-create + wait-for-CREATION_SUCCESSFUL surface tested
across the production CLI workflow).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app
from quicksight_gen.apps.l1_dashboard.datasets import (
    build_all_l1_dashboard_datasets,
)
from quicksight_gen.apps.l2_flow_tracing.app import (
    build_l2_flow_tracing_app,
)
from quicksight_gen.apps.l2_flow_tracing.datasets import (
    build_all_l2_flow_tracing_datasets,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.theme import build_theme


# The two app keys the harness deploys. Aligned with the CLI's
# `APP_CHOICE` constant — adding an app to the harness is one entry
# here + one extension to ``generate_apps`` below.
HARNESS_APPS = ("l1-dashboard", "l2-flow-tracing")


def generate_apps(
    cfg: Config, l2_instance: L2Instance, out_dir: Path,
) -> None:
    """Write the JSON files for both harness apps to ``out_dir``.

    Layout matches the CLI's ``out/`` shape:

        out_dir/
          theme.json
          l1-dashboard-analysis.json
          l1-dashboard-dashboard.json
          l2-flow-tracing-analysis.json
          l2-flow-tracing-dashboard.json
          datasets/
            qs-gen-<l2>-l1-...-dataset.json
            qs-gen-<l2>-l2ft-...-dataset.json
            (...)

    Skips ``datasource.json`` — the harness uses ``cfg.datasource_arn``
    set via ``QS_GEN_DATASOURCE_ARN`` env var; the existing datasource
    is shared across tests, NOT created per-test.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "datasets").mkdir(exist_ok=True)

    # Theme — shared across both apps.
    theme = build_theme(cfg)
    _write_json(out_dir / "theme.json", theme.to_aws_json())

    # L1 dashboard.
    l1_datasets = build_all_l1_dashboard_datasets(cfg, l2_instance)
    for ds in l1_datasets:
        _write_json(
            out_dir / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json(),
        )
    l1_app = build_l1_dashboard_app(cfg, l2_instance=l2_instance)
    _write_json(
        out_dir / "l1-dashboard-analysis.json",
        l1_app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out_dir / "l1-dashboard-dashboard.json",
        l1_app.emit_dashboard().to_aws_json(),
    )

    # L2 Flow Tracing.
    l2ft_datasets = build_all_l2_flow_tracing_datasets(cfg, l2_instance)
    for ds in l2ft_datasets:
        _write_json(
            out_dir / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json(),
        )
    l2ft_app = build_l2_flow_tracing_app(cfg, l2_instance=l2_instance)
    _write_json(
        out_dir / "l2-flow-tracing-analysis.json",
        l2ft_app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out_dir / "l2-flow-tracing-dashboard.json",
        l2ft_app.emit_dashboard().to_aws_json(),
    )


def extract_dashboard_ids(out_dir: Path) -> dict[str, str]:
    """Return ``{app_name: dashboard_id}`` by reading both apps'
    -dashboard.json files.

    The per-app dashboard JSON lives at ``out_dir/<app>-dashboard.json``
    and carries a top-level ``DashboardId`` field that ``common.deploy``
    uses as the QS resource id. Pulling it back out is the cheapest
    way to recover the deploy's actual ids without parsing
    ``deploy()`` stdout or monkeypatching its return signature.
    """
    ids: dict[str, str] = {}
    for app_name in HARNESS_APPS:
        path = out_dir / f"{app_name}-dashboard.json"
        if not path.exists():
            raise FileNotFoundError(
                f"expected {path!r} after generate_apps(); did the apply "
                f"step skip {app_name!r}?"
            )
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        ids[app_name] = payload["DashboardId"]
    return ids


def build_embed_urls(
    *,
    aws_account_id: str,
    aws_region: str,
    dashboard_ids: dict[str, str],
    user_arn: str | None = None,
) -> dict[str, str]:
    """Generate one embed URL per (app_name, dashboard_id).

    Takes ``aws_region`` (the dashboard's region) — embed URLs MUST
    be signed by a client created in the dashboard region (NOT the
    identity region; see ``generate_dashboard_embed_url`` docstring
    for the details + the M.4.1.i bug history). The earlier signature
    took a pre-built client, which made it possible to pass the wrong
    region's client and surface the cryptic "We can't open that
    dashboard" error page. This signature makes that bug
    unrepresentable: caller passes a region string, helper builds
    the client.

    Embed URLs are single-use; caller must scope to per-test, not
    session, so a re-entrant test gets a fresh URL.
    """
    from quicksight_gen.common.browser.helpers import (
        generate_dashboard_embed_url,
    )

    urls: dict[str, str] = {}
    for app_name, dashboard_id in dashboard_ids.items():
        urls[app_name] = generate_dashboard_embed_url(
            aws_account_id=aws_account_id,
            aws_region=aws_region,
            dashboard_id=dashboard_id,
            user_arn=user_arn,
        )
    return urls


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON dict to disk with the same formatting the CLI's
    ``_write_json`` uses (2-space indent, no sort_keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
