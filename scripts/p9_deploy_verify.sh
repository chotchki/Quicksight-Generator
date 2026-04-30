#!/usr/bin/env bash
#
# P.9 — full per-dialect deploy verify against live Aurora + RDS Oracle.
#
# Codifies the manual P.5.b/P.5.c/P.6.b/P.6.c verification:
#   1. quicksight-gen demo apply --all (writes JSON + applies schema +
#      seed + matview refresh against the live DB)
#   2. tests/integration/verify_demo_apply.py (asserts the locked
#      per-prefix matview row counts the seed produces)
#   3. quicksight-gen deploy --all (pushes the JSON to AWS, polls each
#      async resource to terminal state — non-zero exit on any
#      CREATION_FAILED).
#
# Run end-to-end across both dialects, or one at a time.
#
# Usage:
#   ./scripts/p9_deploy_verify.sh                   # both dialects
#   ./scripts/p9_deploy_verify.sh postgres          # PG only
#   ./scripts/p9_deploy_verify.sh oracle            # Oracle only
#   ./scripts/p9_deploy_verify.sh --skip-deploy     # apply + verify, no AWS
#
# Env vars:
#   PG_CONFIG        path to PG config (default: run/config.postgres.yaml)
#   ORACLE_CONFIG    path to Oracle config (default: run/config.oracle.yaml)
#
# Exit codes:
#   0 — every requested dialect passed apply + verify + deploy
#   1 — at least one stage failed; full output above

set -euo pipefail

PG_CONFIG="${PG_CONFIG:-run/config.postgres.yaml}"
ORACLE_CONFIG="${ORACLE_CONFIG:-run/config.oracle.yaml}"

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

verify_one() {
  local dialect="$1"
  local config out url
  case "$dialect" in
    postgres) config="$PG_CONFIG"; out="run/out-postgres" ;;
    oracle)   config="$ORACLE_CONFIG"; out="run/out-oracle" ;;
  esac

  echo
  echo "============================================================"
  echo "  $dialect — config=$config out=$out"
  echo "============================================================"

  echo "--> demo apply --all"
  .venv/bin/quicksight-gen demo apply --all -c "$config" -o "$out"

  echo "--> verify row counts"
  url=$(.venv/bin/python -c "
import yaml
with open('$config') as f: print(yaml.safe_load(f)['demo_database_url'])
")
  .venv/bin/python tests/integration/verify_demo_apply.py \
    --dialect "$dialect" --url "$url"

  if [ "$SKIP_DEPLOY" -eq 1 ]; then
    echo "--> deploy --all (SKIPPED via --skip-deploy)"
    return 0
  fi

  echo "--> deploy --all"
  .venv/bin/quicksight-gen deploy --all -c "$config" -o "$out"
}

for dialect in "${DIALECTS[@]}"; do
  verify_one "$dialect"
done

echo
echo "============================================================"
echo "  P.9 ALL CLEAR — verified: ${DIALECTS[*]}"
echo "============================================================"
