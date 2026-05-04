"""V.1.b — config.yaml ↔ L2 institution YAML boundary enforcement.

The loader is the single chokepoint that distinguishes "a config file
the operator typed by hand" from "any other YAML in the repo". The
strict-allowlist behavior here turns every silent typo (theme: in
config.yaml, l2_instance_prefix hardcoded) into a loud failure with a
pointer at where the field actually belongs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quicksight_gen.common.config import load_config


def _write_yaml(tmp_path: Path, body: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    return p


def test_minimal_valid_config_loads(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
    })
    cfg = load_config(p)
    assert cfg.aws_account_id == "111122223333"


def test_full_valid_config_loads(tmp_path: Path) -> None:
    """Every allowlisted key together — sanity check the allowlist
    isn't accidentally too narrow."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-2",
        "datasource_arn": "arn:aws:quicksight:us-east-2:111122223333:datasource/x",
        "resource_prefix": "qs-gen-test",
        "principal_arns": ["arn:aws:iam::111122223333:user/u"],
        "extra_tags": {"Owner": "team"},
        "demo_database_url": "postgresql://u:p@h:5432/d",
        "dialect": "postgres",
        "signing": {
            "key_path": "k.pem",
            "cert_path": "c.pem",
        },
        "tagging_enabled": False,
    })
    cfg = load_config(p)
    assert cfg.signing is not None
    assert cfg.dialect.value == "postgres"
    assert cfg.tagging_enabled is False


def test_tagging_enabled_defaults_to_true(tmp_path: Path) -> None:
    """The override is opt-in. Omitting it leaves cleanup's
    fail-CLOSED tag-based isolation intact."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
    })
    cfg = load_config(p)
    assert cfg.tagging_enabled is True


def test_tagging_enabled_false_omits_tags_kwarg(tmp_path: Path) -> None:
    """``cfg.tags()`` returns ``None`` when tagging is disabled —
    ``_strip_nones`` then drops the ``Tags`` field from the AWS JSON
    so the boto3 ``Create*`` call carries no ``Tags`` kwarg, keeping
    the IAM principal off ``quicksight:TagResource``."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "tagging_enabled": False,
    })
    cfg = load_config(p)
    assert cfg.tags() is None


def test_tagging_enabled_true_populates_tags_kwarg(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "resource_prefix": "qs-customprefix",
        "extra_tags": {"Owner": "team"},
    })
    cfg = load_config(p)
    tags = cfg.tags()
    assert tags is not None
    keys = {tag.Key for tag in tags}
    assert {"ManagedBy", "ResourcePrefix", "Owner"} <= keys


def test_tagging_enabled_non_bool_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "tagging_enabled": "false",  # YAML string, not bool
    })
    with pytest.raises(ValueError, match="tagging_enabled must be a bool"):
        load_config(p)


@pytest.mark.parametrize("leaked_key", [
    "theme", "persona", "rails", "accounts", "chains",
    "transfer_templates", "account_templates", "limit_schedules",
    "instance", "description", "seed_hash",
])
def test_l2_only_key_in_config_yaml_rejects(
    tmp_path: Path, leaked_key: str,
) -> None:
    """Dropping any L2 institution field into config.yaml is the most
    common misedit. Each one must error with a pointer at the L2 YAML."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        leaked_key: "anything",
    })
    with pytest.raises(ValueError, match="L2 institution YAML"):
        load_config(p)


def test_l2_instance_prefix_in_config_yaml_rejects(tmp_path: Path) -> None:
    """The prefix is computed from the L2 instance.instance field at
    CLI time. Hand-setting it in config.yaml is a sign the user has
    bypassed `--l2`."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "l2_instance_prefix": "spec_example",
    })
    with pytest.raises(ValueError, match="derived from the L2"):
        load_config(p)


def test_unknown_key_rejects(tmp_path: Path) -> None:
    """Random typos / stale keys don't sneak through silently."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "theme_preset": "sasquatch-bank",  # removed in N.4
    })
    with pytest.raises(ValueError, match="unknown config keys"):
        load_config(p)


def test_legacy_principal_arn_singular_still_works(tmp_path: Path) -> None:
    """Backwards compat — singular `principal_arn` accepted alongside
    the canonical plural form."""
    p = _write_yaml(tmp_path, {
        "aws_account_id": "111122223333",
        "aws_region": "us-east-1",
        "datasource_arn": "arn:aws:quicksight:us-east-1:111122223333:datasource/x",
        "principal_arn": "arn:aws:iam::111122223333:user/legacy",
    })
    cfg = load_config(p)
    assert cfg.principal_arns == ["arn:aws:iam::111122223333:user/legacy"]


def test_run_postgres_config_still_loads() -> None:
    """Sanity: the operator's actual postgres config in run/ still
    parses cleanly under the new strict rules."""
    p = Path(__file__).parent.parent.parent / "run" / "config.postgres.yaml"
    if not p.exists():
        pytest.skip(f"{p} not present")
    cfg = load_config(p)
    assert cfg.dialect.value == "postgres"


def test_run_oracle_config_still_loads() -> None:
    p = Path(__file__).parent.parent.parent / "run" / "config.oracle.yaml"
    if not p.exists():
        pytest.skip(f"{p} not present")
    cfg = load_config(p)
    assert cfg.dialect.value == "oracle"
