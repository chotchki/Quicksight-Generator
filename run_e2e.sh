#!/usr/bin/env bash
#
# One-shot e2e runner: regenerate JSON, redeploy to AWS, run e2e tests.
#
# Usage:
#   ./run_e2e.sh                  # generate, deploy, then run all e2e tests
#   ./run_e2e.sh api              # only API tests (skip browser)
#   ./run_e2e.sh browser          # only browser tests
#   ./run_e2e.sh --skip-deploy    # skip generate+deploy, just run tests
#
# Env vars (optional):
#   QS_E2E_PAGE_TIMEOUT   page load timeout in ms (default 30000)
#   QS_E2E_VISUAL_TIMEOUT per-visual timeout in ms (default 10000)
#   QS_E2E_USER_ARN       override the QuickSight user ARN for embed URL

set -euo pipefail

CONFIG=${CONFIG:-run/config.yaml}
OUT_DIR=${OUT_DIR:-run/out}
SKIP_DEPLOY=false
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-deploy) SKIP_DEPLOY=true; shift ;;
        api)     PYTEST_ARGS+=("-m" "api"); shift ;;
        browser) PYTEST_ARGS+=("-m" "browser"); shift ;;
        *)       PYTEST_ARGS+=("$1"); shift ;;
    esac
done

if [ "$SKIP_DEPLOY" = false ]; then
    echo "==> Regenerating JSON ($CONFIG -> $OUT_DIR)"
    .venv/bin/quicksight-gen generate -c "$CONFIG" -o "$OUT_DIR"

    echo "==> Deploying to AWS"
    ./deploy.sh "$OUT_DIR"
fi

echo "==> Running e2e tests"
QS_GEN_E2E=1 .venv/bin/python -m pytest tests/e2e "${PYTEST_ARGS[@]}"
