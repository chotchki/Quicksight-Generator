#!/usr/bin/env bash
#
# P.9 — full per-(dialect, L2-instance) deploy verify against live
# Aurora + RDS Oracle.
#
# Codifies the manual P.5.b/P.5.c/P.6.b/P.6.c verification, extended
# in P.9 to loop over both shipped L2 example YAMLs:
#   1. quicksight-gen demo apply --all --l2-instance <yaml>
#      (writes JSON + applies schema + seed + matview refresh against
#       the live DB for that L2 instance's prefix)
#   2. tests/integration/verify_demo_apply.py
#      (asserts the per-prefix matview row counts: exact for
#       spec_example, smoke ≥1 for sasquatch_pr until counts get
#       locked)
#   3. quicksight-gen deploy --all --l2-instance <yaml>
#      (pushes the JSON to AWS, polls each async resource to terminal
#       state — non-zero exit on any CREATION_FAILED)
#
# Default matrix: 2 dialects × 2 L2 examples = 4 cells. Each cell
# touches its own per-(dialect, L2-prefix) tag namespace, so cells
# don't sweep each other's resources.
#
# Usage:
#   ./scripts/p9_deploy_verify.sh                   # full 2×2 matrix
#   ./scripts/p9_deploy_verify.sh postgres          # PG × both L2s
#   ./scripts/p9_deploy_verify.sh oracle            # Oracle × both L2s
#   ./scripts/p9_deploy_verify.sh --skip-deploy     # apply + verify only
#
# Env vars:
#   PG_CONFIG       (default: run/config.postgres.yaml)
#   ORACLE_CONFIG   (default: run/config.oracle.yaml)
#   L2_INSTANCES    (space-separated paths; default both shipped examples)
#
# Exit codes:
#   0 — every requested cell passed apply + verify + deploy
#   1 — at least one stage failed; full output above

set -euo pipefail

PG_CONFIG="${PG_CONFIG:-run/config.postgres.yaml}"
ORACLE_CONFIG="${ORACLE_CONFIG:-run/config.oracle.yaml}"
L2_INSTANCES="${L2_INSTANCES:-tests/l2/spec_example.yaml tests/l2/sasquatch_pr.yaml}"

DIALECTS=()
SKIP_DEPLOY=0
for arg in "$@"; do
  case "$arg" in
    postgres|oracle) DIALECTS+=("$arg") ;;
    --skip-deploy)   SKIP_DEPLOY=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done
if [ ${#DIALECTS[@]} -eq 0 ]; then
  DIALECTS=(postgres oracle)
fi

verify_cell() {
  local dialect="$1" l2_path="$2"
  local config out url l2_prefix smoke_flag
  case "$dialect" in
    postgres) config="$PG_CONFIG" ;;
    oracle)   config="$ORACLE_CONFIG" ;;
  esac
  l2_prefix="$(basename "$l2_path" .yaml)"
  out="run/out-${dialect}-${l2_prefix}"

  # Locked counts only exist for spec_example so far; sasquatch_pr
  # gets the smoke (≥1 row) check until counts get locked.
  if [ "$l2_prefix" = "spec_example" ]; then
    smoke_flag=""
  else
    smoke_flag="--smoke"
  fi

  echo
  echo "============================================================"
  echo "  $dialect × $l2_prefix — out=$out"
  echo "============================================================"

  echo "--> demo apply --all --l2-instance $l2_path  (Inv + Exec JSON + DB)"
  .venv/bin/quicksight-gen demo apply --all -c "$config" -o "$out" \
    --l2-instance "$l2_path"

  echo "--> generate l1-dashboard --l2-instance $l2_path"
  .venv/bin/quicksight-gen generate -c "$config" -o "$out" l1-dashboard \
    --l2-instance "$l2_path"

  echo "--> generate l2-flow-tracing --l2-instance $l2_path"
  .venv/bin/quicksight-gen generate -c "$config" -o "$out" l2-flow-tracing \
    --l2-instance "$l2_path"

  echo "--> verify row counts (--prefix $l2_prefix $smoke_flag)"
  url=$(.venv/bin/python -c "
import yaml
with open('$config') as f: print(yaml.safe_load(f)['demo_database_url'])
")
  .venv/bin/python tests/integration/verify_demo_apply.py \
    --dialect "$dialect" --url "$url" \
    --prefix "$l2_prefix" $smoke_flag

  if [ "$SKIP_DEPLOY" -eq 1 ]; then
    echo "--> deploy --all (SKIPPED via --skip-deploy)"
    return 0
  fi

  echo "--> deploy --all --l2-instance $l2_path"
  .venv/bin/quicksight-gen deploy --all -c "$config" -o "$out" \
    --l2-instance "$l2_path"
}

for dialect in "${DIALECTS[@]}"; do
  for l2_path in $L2_INSTANCES; do
    verify_cell "$dialect" "$l2_path"
  done
done

echo
echo "============================================================"
echo "  P.9 ALL CLEAR — verified: ${DIALECTS[*]} × $L2_INSTANCES"
echo "============================================================"
