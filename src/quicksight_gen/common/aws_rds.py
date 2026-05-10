"""Y.2.gate.l — Thin RDS lifecycle wrapper for the start/stop commands.

`./run_tests.sh up aws` / `down aws` / `status` (cmd_up / cmd_down /
cmd_status in `_dev/runner.py`) call into here. Same shape as the four
existing boto3 wrappers (`common/deploy.py`, `common/cleanup.py`,
`common/browser/helpers.py`, `_dev/runner.py`) — one client construction
site per concern, on the boto3-direct lint allowlist.

Aurora vs single-instance Oracle: PG runs on Aurora (cluster-scoped —
`{start,stop,describe}_db_cluster*`); Oracle on RDS (instance-scoped —
`{start,stop,describe}_db_instance*`). Two parallel families, identical
shape; the runner picks the right family via cfg field name.

All operations idempotent: if the resource is already in the requested
terminal state (started → start = no-op, stopped → stop = no-op), the
boto3 InvalidDBClusterStateFault / InvalidDBInstanceState is swallowed
and we return the current status. Any other error (NotFound, auth,
network) propagates — those are operator-actionable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

# boto3-stubs[rds] gives RDSClient typing. We mark it as
# TYPE_CHECKING-only so the runtime path doesn't depend on the stub
# package; pyproject.toml::dev extras pull it in for local development.
if TYPE_CHECKING:
    from mypy_boto3_rds.client import RDSClient
else:
    RDSClient = object


# Resource lifecycle states from RDS docs. We don't enumerate every state
# (RDS has ~25), only the ones the runner branches on. Anything else
# falls through as "unknown" and the operator triages.
RdsStatus = Literal[
    "available", "starting", "stopped", "stopping",
    "creating", "modifying", "rebooting", "unknown",
]

# Terminal states for our purposes — the resource is in a stable state
# we can act on. "starting"/"stopping" are transient; the runner polls
# until they resolve.
TERMINAL_STATES: frozenset[str] = frozenset({"available", "stopped"})


@dataclass(frozen=True)
class RdsResource:
    """Identifies one RDS resource for the lifecycle commands.

    `kind` discriminates which boto3 family to call (`cluster` for
    Aurora PG, `instance` for non-Aurora Oracle). `identifier` is the
    operator-facing name (cfg.aws_pg_cluster_id or
    cfg.aws_oracle_instance_id). `aws_region` matches cfg.aws_region —
    same client per region.
    """
    kind: Literal["cluster", "instance"]
    identifier: str
    aws_region: str


def _rds_client(aws_region: str) -> RDSClient:
    """Single boto3.client('rds') construction site. Allowlisted by
    `tests/unit/test_typing_smells.py::Boto3DirectCheck`."""
    import boto3

    client: RDSClient = boto3.client(  # pyright: ignore[reportUnknownMemberType]: boto3-stubs huge overload union confuses pyright (matches browser/helpers.py pattern)
        "rds", region_name=aws_region,
    )
    return client


def get_status(resource: RdsResource) -> RdsStatus:
    """Return the current RDS state. Raises if the identifier doesn't
    exist (`DBClusterNotFoundFault` / `DBInstanceNotFoundFault`) — that
    means the operator's cfg points at a typo or a deleted resource.

    Status maps directly from the RDS API field — `Status` for
    clusters, `DBInstanceStatus` for instances.
    """
    client = _rds_client(resource.aws_region)
    if resource.kind == "cluster":
        resp = client.describe_db_clusters(
            DBClusterIdentifier=resource.identifier,
        )
        clusters = resp.get("DBClusters", [])
        if not clusters:
            raise RuntimeError(
                f"RDS describe_db_clusters returned no clusters for "
                f"{resource.identifier!r} — check cfg.aws_pg_cluster_id"
            )
        raw = clusters[0].get("Status", "unknown")
    else:
        resp = client.describe_db_instances(
            DBInstanceIdentifier=resource.identifier,
        )
        instances = resp.get("DBInstances", [])
        if not instances:
            raise RuntimeError(
                f"RDS describe_db_instances returned no instances for "
                f"{resource.identifier!r} — check "
                f"cfg.aws_oracle_instance_id"
            )
        raw = instances[0].get("DBInstanceStatus", "unknown")
    # Narrow to the Literal union; "unknown" is the catch-all so we
    # never lose triage info on a state we don't enumerate.
    return raw if raw in (
        "available", "starting", "stopped", "stopping",
        "creating", "modifying", "rebooting",
    ) else "unknown"


def start(resource: RdsResource) -> RdsStatus:
    """Start the RDS resource; idempotent — already-running returns
    the current status without raising.

    Returns the post-call status (`starting` for cold-start,
    `available` for already-up). Caller polls via `get_status` until
    the status hits `available`.
    """
    client = _rds_client(resource.aws_region)
    try:
        if resource.kind == "cluster":
            client.start_db_cluster(DBClusterIdentifier=resource.identifier)
        else:
            client.start_db_instance(DBInstanceIdentifier=resource.identifier)
    except Exception as exc:
        # boto3 botocore.exceptions.ClientError carries .response
        # ['Error']['Code']; idempotent shape: if the resource is
        # already in the target state, RDS raises one of these:
        #   - InvalidDBClusterStateFault (cluster already running)
        #   - InvalidDBInstanceState (instance already running)
        # Everything else propagates.
        code = _client_error_code(exc)
        if code in ("InvalidDBClusterStateFault", "InvalidDBInstanceState"):
            # Already started or starting — get_status confirms.
            return get_status(resource)
        raise
    return get_status(resource)


def stop(resource: RdsResource) -> RdsStatus:
    """Stop the RDS resource; idempotent — already-stopped returns
    the current status without raising.

    Aurora `stop_db_cluster` requires the cluster to be in `available`
    state; if currently `starting`, RDS rejects with
    `InvalidDBClusterStateFault`. Same shape as `start`: caller polls
    until the status hits `stopped`.

    Note: stopped clusters auto-restart after 7 days (AWS limit). The
    `up` command's `start_db_cluster` is a no-op when already started,
    so a 7-day idle gap doesn't break operator workflow.
    """
    client = _rds_client(resource.aws_region)
    try:
        if resource.kind == "cluster":
            client.stop_db_cluster(DBClusterIdentifier=resource.identifier)
        else:
            client.stop_db_instance(DBInstanceIdentifier=resource.identifier)
    except Exception as exc:
        code = _client_error_code(exc)
        if code in ("InvalidDBClusterStateFault", "InvalidDBInstanceState"):
            return get_status(resource)
        raise
    return get_status(resource)


def _client_error_code(exc: Exception) -> str | None:
    """Extract the boto3 ClientError code without importing botocore
    at module load. ClientError exposes ``.response['Error']['Code']``
    when raised by an AWS API call.
    """
    from typing import cast
    response = cast("dict[str, object] | None", getattr(exc, "response", None))
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    error_dict = cast("dict[str, object]", error)
    code = error_dict.get("Code")
    return str(code) if code is not None else None
