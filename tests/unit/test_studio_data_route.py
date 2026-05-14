"""Studio data-shaping panel route tests (X.4.h.1).

Locks the contract for the new ``/data`` mode shell:

- ``GET /data`` returns 200 + a page that carries the three landmark
  elements the trainer mode is built around (knob strip, timeline
  column, training column). Knob widgets land in h.2-h.5; this test
  just guarantees the page-shell selectors are stable for that wiring
  to bind to.
- The home + diagram chrome pick up a ``→ data`` nav link so the new
  mode is discoverable from every existing studio page.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

starlette = pytest.importorskip("starlette")
TestClient = pytest.importorskip("starlette.testclient").TestClient

from quicksight_gen.common.html._smoke_app import (
    SMOKE_FILTER_SPECS,
    build_smoke_app,
    stub_money_trail_fetcher,
)
from quicksight_gen.common.html._studio_routes import make_studio_routes
from quicksight_gen.common.html.server import ServedDashboard, make_app
from quicksight_gen.common.l2.cache import L2InstanceCache
from tests._test_helpers import make_test_config


_FIXTURES = Path(__file__).resolve().parent.parent / "l2"


@pytest.fixture
def writable_l2_yaml(tmp_path: Path) -> Iterator[Path]:
    src = _FIXTURES / "spec_example.yaml"
    dst = tmp_path / "spec_example.yaml"
    shutil.copy(src, dst)
    yield dst


def _build_app(yaml_path: Path) -> object:
    cache = L2InstanceCache.from_path(yaml_path)
    cfg = make_test_config()
    tree_app, sheet = build_smoke_app(cfg)
    served = ServedDashboard(
        tree_app=tree_app, sheet=sheet, title="smoke",
        data_fetcher=stub_money_trail_fetcher,
        filter_specs=SMOKE_FILTER_SPECS,
    )
    return make_app(
        dashboards={"smoke": served},
        studio_routes=make_studio_routes(cache),
    )


def test_data_route_returns_200_with_landmarks(
    writable_l2_yaml: Path,
) -> None:
    """GET /data renders the trainer-mode page-shell with chrome bar,
    knob strip, timeline column, and training column landmarks."""
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        resp = c.get("/data")
        assert resp.status_code == 200
        body = resp.text

    # Three landmark elements h.2-h.9 will bind to.
    assert 'id="data-knobs"' in body, "knob-strip placeholder missing"
    assert 'id="data-timeline"' in body, "timeline column missing"
    assert 'id="data-training"' in body, "training column missing"
    # Aria labels matter for the screen-reader landmark map (and give
    # the Playwright e2e in h.8.c stable role-based selectors).
    assert 'aria-label="Plant timeline"' in body
    assert 'aria-label="Training pane"' in body


def test_data_route_carries_deploy_button(
    writable_l2_yaml: Path,
) -> None:
    """The trainer page exposes the same Deploy button the home page
    does, so the operator can re-deploy without bouncing back to /."""
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        body = c.get("/data").text

    assert 'id="deploy-btn"' in body
    assert 'id="deploy-status"' in body
    assert 'function quicksightDeploy()' in body


def test_data_route_carries_back_to_landing_link(
    writable_l2_yaml: Path,
) -> None:
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        body = c.get("/data").text

    assert '<a class="nav-link" href="/">← landing</a>' in body
    assert '<a class="nav-link" href="/diagram">→ diagram</a>' in body


def test_home_chrome_links_to_data(writable_l2_yaml: Path) -> None:
    """X.4.h.1.b — landing page chrome carries a `→ data` link."""
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        body = c.get("/").text

    assert '<a class="nav-link" href="/data">→ data</a>' in body


def test_diagram_chrome_links_to_data(writable_l2_yaml: Path) -> None:
    """X.4.h.1.b — diagram page chrome carries a `→ data` link."""
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        body = c.get("/diagram").text

    assert '<a class="nav-link" href="/data">→ data</a>' in body


def test_diagram_chrome_omits_data_link_in_embed_mode(
    writable_l2_yaml: Path,
) -> None:
    """The diagram is iframed inside the home page in embed mode; the
    embed strips the studio-header so the page doesn't carry two nav
    bars. The data link rides on that header so it should be absent
    in embed mode too."""
    app = _build_app(writable_l2_yaml)
    with TestClient(app) as c:  # type: ignore[arg-type]: TestClient stubs accept ASGI apps but the inferred return type from make_app is Any
        body = c.get("/diagram?embed=1").text

    # Whole studio-header is omitted in embed mode (existing X.4.f.8
    # behavior); just sanity-check the data link doesn't sneak through.
    assert 'href="/data"' not in body
