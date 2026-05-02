#!/usr/bin/env bash
#
# P.9 — full per-(dialect, L2-instance) deploy verify against live
# Aurora + RDS Oracle.
#
# Codifies the manual P.5.b/P.5.c/P.6.b/P.6.c verification, extended
# in P.9 to loop over both shipped L2 example YAMLs. Q.3.a (v8.0.0)
# explicitly chains the four artifact groups in place of the legacy
# `demo apply --all` bundle:
#   1. quicksight-gen schema apply --execute --l2 <yaml>
#      (creates per-prefix tables + matviews on the live DB)
#   2. quicksight-gen data apply --execute --l2 <yaml>
#      (inserts the 90-day baseline + plant overlays)
#   3. quicksight-gen data refresh --execute --l2 <yaml>
#      (refreshes the L1 invariant + Investigation matviews)
#   4. quicksight-gen json apply --l2 <yaml> -o <out>
#      (writes JSON for all 4 apps to <out>/)
#   5. tests/integration/verify_demo_apply.py
#      (asserts the per-prefix matview row counts: exact for
#       spec_example, smoke ≥1 for sasquatch_pr until counts get
#       locked)
#   6. quicksight-gen json apply --execute --l2 <yaml> -o <out>
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

  echo "--> schema apply --execute  (DB)"
  .venv/bin/quicksight-gen schema apply -c "$config" --l2 "$l2_path" --execute

  echo "--> data apply --execute  (DB)"
  .venv/bin/quicksight-gen data apply -c "$config" --l2 "$l2_path" --execute

  echo "--> data refresh --execute  (matviews)"
  .venv/bin/quicksight-gen data refresh -c "$config" --l2 "$l2_path" --execute

  echo "--> json apply  (write JSON for all 4 apps)"
  .venv/bin/quicksight-gen json apply -c "$config" -o "$out" --l2 "$l2_path"

  echo "--> verify row counts (--prefix $l2_prefix $smoke_flag)"
  url=$(.venv/bin/python -c "
import yaml
with open('$config') as f: print(yaml.safe_load(f)['demo_database_url'])
")
  .venv/bin/python tests/integration/verify_demo_apply.py \
    --dialect "$dialect" --url "$url" \
    --prefix "$l2_prefix" $smoke_flag

  if [ "$SKIP_DEPLOY" -eq 1 ]; then
    echo "--> json apply --execute (SKIPPED via --skip-deploy)"
    return 0
  fi

  echo "--> json apply --execute  (push to AWS)"
  .venv/bin/quicksight-gen json apply -c "$config" -o "$out" \
    --l2 "$l2_path" --execute
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
