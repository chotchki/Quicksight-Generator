#!/usr/bin/env bash
#
# M.2.6 verification runner — deploy v6 schema + plant seed +
# verify L1 invariant views surface the planted scenarios.
#
# Usage:
#   ./m2_6_verify.sh                    # full deploy + verify
#   ./m2_6_verify.sh --schema-only      # apply schema; no seed/verify
#   ./m2_6_verify.sh --no-deploy        # just run the verify queries
#   ./m2_6_verify.sh --skip-warmup      # skip the Aurora cold-start tax
#
# Env vars (optional):
#   CONFIG    path to config YAML (default: run/config.yaml)
#
# Exit codes:
#   0 — all assertions passed
#   1 — at least one scenario didn't surface
#   2 — config / connection error before assertions could run

set -euo pipefail

CONFIG="${CONFIG:-run/config.yaml}"

echo "==> M.2.6 verify (config=$CONFIG)"
.venv/bin/python scripts/m2_6_verify.py --config "$CONFIG" "$@"
