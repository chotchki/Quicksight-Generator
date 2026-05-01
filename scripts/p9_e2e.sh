#!/usr/bin/env bash
#
# P.9 — run e2e tests against the deployed 2×2 matrix
# (postgres + oracle × spec_example + sasquatch_pr).
#
# Pre-requisite: scripts/p9_deploy_verify.sh has run cleanly so the 4
# cells' dashboards exist on AWS. This script does NOT redeploy.
#
# Drives the existing run_e2e.sh per-cell via env vars:
#   CONFIG                  → which AWS config (PG or Oracle)
#   OUT_DIR                 → which generated JSON to read
#   QS_GEN_CONFIG           → conftest.py cfg fixture override
#   QS_GEN_TEST_L2_INSTANCE → L2 instance YAML override (P.9)
#
# Usage:
#   ./scripts/p9_e2e.sh                   # full 2×2 matrix
#   ./scripts/p9_e2e.sh postgres          # PG × both L2s
#   ./scripts/p9_e2e.sh oracle            # Oracle × both L2s
#
# Exit codes:
#   0 — every requested cell passed e2e
#   1 — at least one cell failed; per-cell output above

set -uo pipefail

PG_CONFIG="${PG_CONFIG:-run/config.postgres.yaml}"
ORACLE_CONFIG="${ORACLE_CONFIG:-run/config.oracle.yaml}"
L2_INSTANCES="${L2_INSTANCES:-tests/l2/spec_example.yaml tests/l2/sasquatch_pr.yaml}"

DIALECTS=()
for arg in "$@"; do
  case "$arg" in
    postgres|oracle) DIALECTS+=("$arg") ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done
if [ ${#DIALECTS[@]} -eq 0 ]; then
  DIALECTS=(postgres oracle)
fi

results=()
overall_exit=0

for dialect in "${DIALECTS[@]}"; do
  for l2_path in $L2_INSTANCES; do
    case "$dialect" in
      postgres) config="$PG_CONFIG" ;;
      oracle)   config="$ORACLE_CONFIG" ;;
    esac
    l2_prefix="$(basename "$l2_path" .yaml)"
    out="run/out-${dialect}-${l2_prefix}"
    cell_label="${dialect}×${l2_prefix}"

    echo
    echo "============================================================"
    echo "  e2e: $cell_label  (config=$config, out=$out, l2=$l2_path)"
    echo "============================================================"

    CONFIG="$config" \
    OUT_DIR="$out" \
    QS_GEN_CONFIG="$config" \
    QS_GEN_TEST_L2_INSTANCE="$l2_path" \
      ./run_e2e.sh --skip-deploy
    cell_exit=$?

    if [ $cell_exit -eq 0 ]; then
      results+=("✓ $cell_label")
    else
      results+=("✗ $cell_label (exit $cell_exit)")
      overall_exit=1
    fi
  done
done

echo
echo "============================================================"
echo "  P.9 e2e summary"
echo "============================================================"
for r in "${results[@]}"; do echo "  $r"; done
exit $overall_exit
