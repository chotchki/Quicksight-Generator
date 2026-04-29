#!/usr/bin/env bash
#
# One-shot e2e runner: regenerate JSON, redeploy to AWS, run e2e tests.
#
# Usage:
#   ./run_e2e.sh                  # generate, deploy, then run all e2e tests
#   ./run_e2e.sh api              # only API tests (skip browser)
#   ./run_e2e.sh browser          # only browser tests
#   ./run_e2e.sh --skip-deploy    # skip generate+deploy, just run tests
#   ./run_e2e.sh --parallel N     # run e2e with pytest-xdist at -n N (default 4)
#   ./run_e2e.sh --parallel 1     # force serial
#   ./run_e2e.sh --harness        # run ONLY the M.4.1 end-to-end harness
#                                 # (skips production deploy + skips the rest
#                                 #  of the e2e suite — opt-in for nightly /
#                                 #  pre-release validation; not for fast
#                                 #  inner-loop dev work)
#
# --harness mode notes:
#   - Each harness test deploys per-test ephemeral QuickSight resources
#     and tears them down via tag-filter sweep at teardown. Unlike the
#     rest of the e2e suite, no pre-existing dashboard is required.
#   - Expected runtime: ~5–10 min per L2_INSTANCES entry (currently 3 →
#     wall clock ~5–10 min at --parallel 3 with xdist saturation; ~15–30
#     min at --parallel 1).
#   - Triage manifests for failed tests land under tests/e2e/failures/
#     (gitignored); each carries seed_hash, planted_manifest, deployed
#     dashboard ids + embed URLs, matview row counts, and the full
#     pytest traceback.
#
# Env vars (optional):
#   QS_E2E_PAGE_TIMEOUT   page load timeout in ms (default 30000)
#   QS_E2E_VISUAL_TIMEOUT per-visual timeout in ms (default 10000)
#   QS_E2E_USER_ARN       override the QuickSight user ARN for embed URL

set -euo pipefail

CONFIG=${CONFIG:-run/config.yaml}
OUT_DIR=${OUT_DIR:-run/out}
SKIP_DEPLOY=false
HARNESS=false
PARALLEL=4
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-deploy) SKIP_DEPLOY=true; shift ;;
        --harness)     HARNESS=true; shift ;;
        --parallel)    PARALLEL="$2"; shift 2 ;;
        api)     PYTEST_ARGS+=("-m" "api"); shift ;;
        browser) PYTEST_ARGS+=("-m" "browser"); shift ;;
        *)       PYTEST_ARGS+=("$1"); shift ;;
    esac
done

if [ "$PARALLEL" -gt 1 ]; then
    PYTEST_ARGS=("-n" "$PARALLEL" "${PYTEST_ARGS[@]}")
fi

# Pin the L2 fuzz seed once at the parent level so every pytest-xdist
# worker inherits the same value. Without this, each worker imports
# tests/test_l2_seed_contract.py independently and `secrets.randbits(32)`
# resolves to a different seed per worker → the `fuzz-seed-N` parametrize
# id diverges across workers → xdist refuses to run with "Different tests
# were collected between gw0 and gwN". User can still pin manually via
# QS_GEN_FUZZ_SEED=N to reproduce a specific shape.
if [ -z "${QS_GEN_FUZZ_SEED:-}" ]; then
    export QS_GEN_FUZZ_SEED=$(python3 -c 'import secrets; print(secrets.randbits(32))')
    echo "==> Pinned QS_GEN_FUZZ_SEED=$QS_GEN_FUZZ_SEED for this run"
fi

# --harness mode: skip prod deploy + run only the harness file.
# The harness manages its own per-test ephemeral resources, so the
# production deploy is irrelevant (and the rest of the e2e suite
# would conflict by binding to the production resource IDs).
if [ "$HARNESS" = true ]; then
    echo "==> Running M.4.1 end-to-end harness (per-test ephemeral deploys)"
    echo "    L2_INSTANCES × ~5–10 min/instance; xdist=$PARALLEL"
    QS_GEN_E2E=1 .venv/bin/python -m pytest \
        tests/e2e/test_harness_end_to_end.py "${PYTEST_ARGS[@]}"
    exit $?
fi

if [ "$SKIP_DEPLOY" = false ]; then
    echo "==> Regenerating and deploying ($CONFIG -> $OUT_DIR)"
    .venv/bin/quicksight-gen deploy --all --generate -c "$CONFIG" -o "$OUT_DIR"
fi

echo "==> Running e2e tests"
QS_GEN_E2E=1 .venv/bin/python -m pytest tests/e2e "${PYTEST_ARGS[@]}"
