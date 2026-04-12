"""Configuration for QuickSight resource generation.

Reads from a YAML config file or environment variables. All generated
resources reference the datasource and account specified here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    aws_account_id: str
    aws_region: str
    datasource_arn: str | None = None
    resource_prefix: str = "qs-gen"
    principal_arns: list[str] = field(default_factory=list)
    extra_tags: dict[str, str] = field(default_factory=dict)
    theme_preset: str = "default"
    demo_database_url: str | None = None
    late_default_days: int = 30

    def __post_init__(self) -> None:
        # If demo_database_url is set but datasource_arn is not, derive it
        if self.datasource_arn is None and self.demo_database_url is not None:
            ds_id = self.prefixed("demo-datasource")
            self.datasource_arn = (
                f"arn:aws:quicksight:{self.aws_region}:{self.aws_account_id}"
                f":datasource/{ds_id}"
            )
        if self.datasource_arn is None:
            raise ValueError(
                "datasource_arn is required unless demo_database_url is set."
            )

    # Derived helpers
    def tags(self) -> list[dict[str, str]]:
        """Return common + extra tags as the AWS Tag list format."""
        from quicksight_gen.common.models import Tag

        all_tags = [Tag(Key="ManagedBy", Value="quicksight-gen")]
        for key, value in self.extra_tags.items():
            all_tags.append(Tag(Key=key, Value=value))
        return all_tags

    def dataset_arn(self, dataset_id: str) -> str:
        return (
            f"arn:aws:quicksight:{self.aws_region}:{self.aws_account_id}"
            f":dataset/{dataset_id}"
        )

    def theme_arn(self, theme_id: str) -> str:
        return (
            f"arn:aws:quicksight:{self.aws_region}:{self.aws_account_id}"
            f":theme/{theme_id}"
        )

    def prefixed(self, name: str) -> str:
        """Return a resource ID with the configured prefix."""
        return f"{self.resource_prefix}-{name}"


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from a YAML file, falling back to env vars.

    YAML keys map directly to Config fields (snake_case). ``principal_arns``
    may be a single string or a list; a legacy ``principal_arn`` key is also
    accepted as a single string.
    Environment variables use uppercase with QS_GEN_ prefix:
        QS_GEN_AWS_ACCOUNT_ID, QS_GEN_AWS_REGION, QS_GEN_DATASOURCE_ARN,
        QS_GEN_RESOURCE_PREFIX, QS_GEN_PRINCIPAL_ARNS (comma-separated)
    """
    values: dict = {}

    # Try YAML first
    if path is not None:
        p = Path(path)
        if p.exists():
            with p.open() as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, dict):
                values.update(raw)

    # Env vars override YAML
    env_map = {
        "aws_account_id": "QS_GEN_AWS_ACCOUNT_ID",
        "aws_region": "QS_GEN_AWS_REGION",
        "datasource_arn": "QS_GEN_DATASOURCE_ARN",
        "resource_prefix": "QS_GEN_RESOURCE_PREFIX",
        "theme_preset": "QS_GEN_THEME_PRESET",
        "demo_database_url": "QS_GEN_DEMO_DATABASE_URL",
        "late_default_days": "QS_GEN_LATE_DEFAULT_DAYS",
    }
    for cfg_key, env_key in env_map.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            values[cfg_key] = env_val

    env_principals = os.environ.get("QS_GEN_PRINCIPAL_ARNS")
    if env_principals is not None:
        values["principal_arns"] = [
            p.strip() for p in env_principals.split(",") if p.strip()
        ]

    # Validate required fields (datasource_arn not required when demo_database_url is set)
    required = ["aws_account_id", "aws_region"]
    if "demo_database_url" not in values:
        required.append("datasource_arn")
    missing = [k for k in required if k not in values]
    if missing:
        required_env = {
            "aws_account_id": "QS_GEN_AWS_ACCOUNT_ID",
            "aws_region": "QS_GEN_AWS_REGION",
            "datasource_arn": "QS_GEN_DATASOURCE_ARN",
        }
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set them in your config YAML or via environment variables "
            f"({', '.join(required_env[k] for k in missing)})."
        )

    # Extra tags: expect a dict under "extra_tags" in the YAML
    raw_tags = values.get("extra_tags", {})
    extra_tags = dict(raw_tags) if isinstance(raw_tags, dict) else {}

    # Principals: accept ``principal_arns`` (list or str) or legacy
    # ``principal_arn`` (str or list).
    principal_arns: list[str] = []
    for key in ("principal_arns", "principal_arn"):
        raw = values.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            principal_arns.append(raw)
        elif isinstance(raw, list):
            principal_arns.extend(str(item) for item in raw)

    return Config(
        aws_account_id=values["aws_account_id"],
        aws_region=values["aws_region"],
        datasource_arn=values.get("datasource_arn"),
        resource_prefix=values.get("resource_prefix", "qs-gen"),
        principal_arns=principal_arns,
        extra_tags=extra_tags,
        theme_preset=values.get("theme_preset", "default"),
        demo_database_url=values.get("demo_database_url"),
        late_default_days=int(values.get("late_default_days", 30)),
    )
