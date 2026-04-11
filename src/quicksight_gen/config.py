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
    datasource_arn: str
    resource_prefix: str = "qs-gen"
    principal_arn: str | None = None
    extra_tags: dict[str, str] = field(default_factory=dict)

    # Derived helpers
    def tags(self) -> list[dict[str, str]]:
        """Return common + extra tags as the AWS Tag list format."""
        from quicksight_gen.models import Tag

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

    YAML keys map directly to Config fields (snake_case).
    Environment variables use uppercase with QS_GEN_ prefix:
        QS_GEN_AWS_ACCOUNT_ID, QS_GEN_AWS_REGION, QS_GEN_DATASOURCE_ARN,
        QS_GEN_RESOURCE_PREFIX, QS_GEN_PRINCIPAL_ARN
    """
    values: dict[str, str] = {}

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
        "principal_arn": "QS_GEN_PRINCIPAL_ARN",
    }
    for cfg_key, env_key in env_map.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            values[cfg_key] = env_val

    # Validate required fields
    missing = [k for k in ("aws_account_id", "aws_region", "datasource_arn") if k not in values]
    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set them in your config YAML or via environment variables "
            f"({', '.join(env_map[k] for k in missing)})."
        )

    # Extra tags: expect a dict under "extra_tags" in the YAML
    raw_tags = values.get("extra_tags", {})
    extra_tags = dict(raw_tags) if isinstance(raw_tags, dict) else {}

    return Config(
        aws_account_id=values["aws_account_id"],
        aws_region=values["aws_region"],
        datasource_arn=values["datasource_arn"],
        resource_prefix=values.get("resource_prefix", "qs-gen"),
        principal_arn=values.get("principal_arn"),
        extra_tags=extra_tags,
    )
