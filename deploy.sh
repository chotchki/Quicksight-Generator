#!/usr/bin/env bash
#
# Deploy generated QuickSight resources using the AWS CLI.
#
# Usage:
#   1. Generate JSON:  python -m quicksight_gen generate -c config.yaml
#   2. Deploy:         ./deploy.sh [output-dir]
#   3. Delete only:    ./deploy.sh --delete [output-dir]
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - QuickSight Enterprise edition enabled in the target account
#
# This script is idempotent — it deletes existing resources and recreates
# them on each run to avoid update-command parameter mismatches.
# After creation, it polls async resources (analyses, dashboards) until
# they reach a terminal state and reports any failures.

set -euo pipefail
trap 'echo -e "\nInterrupted."; exit 130' INT

DELETE_ONLY=false
if [ "${1:-}" = "--delete" ]; then
    DELETE_ONLY=true
    shift
fi

OUT_DIR="${1:-out}"
AWS_ACCOUNT_ID=$(jq -r '.AwsAccountId' "$OUT_DIR/theme.json")
REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
POLL_INTERVAL=5
POLL_MAX_ATTEMPTS=60   # 5 minutes max

echo "Deploying QuickSight resources from $OUT_DIR"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Region:  $REGION"
echo

# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

# Wait for an analysis to reach a terminal state.
# Prints status and errors. Returns 0 on success, 1 on failure.
wait_for_analysis() {
    local analysis_id="$1"
    local attempt=0
    while [ $attempt -lt $POLL_MAX_ATTEMPTS ]; do
        local result
        result=$(aws quicksight describe-analysis \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --analysis-id "$analysis_id" \
            --region "$REGION" 2>&1) || true

        local status
        status=$(echo "$result" | jq -r '.Analysis.Status // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")

        case "$status" in
            CREATION_SUCCESSFUL|UPDATE_SUCCESSFUL)
                echo "    Status: $status"
                return 0
                ;;
            CREATION_FAILED|UPDATE_FAILED)
                echo "    Status: $status"
                local errors
                errors=$(echo "$result" | jq -r '.Analysis.Errors[]?.Message // empty' 2>/dev/null)
                if [ -n "$errors" ]; then
                    echo "    Errors:"
                    echo "$errors" | sed 's/^/      /'
                fi
                return 1
                ;;
            DELETED)
                echo "    Status: DELETED (unexpected)"
                return 1
                ;;
            *)
                attempt=$((attempt + 1))
                if [ $((attempt % 6)) -eq 0 ]; then
                    echo "    Still waiting... ($status, ${attempt}/${POLL_MAX_ATTEMPTS})"
                fi
                sleep "$POLL_INTERVAL"
                ;;
        esac
    done
    echo "    Timed out waiting for analysis $analysis_id (last status: $status)"
    return 1
}

# Wait for a dashboard to reach a terminal state.
wait_for_dashboard() {
    local dashboard_id="$1"
    local attempt=0
    while [ $attempt -lt $POLL_MAX_ATTEMPTS ]; do
        local result
        result=$(aws quicksight describe-dashboard \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --dashboard-id "$dashboard_id" \
            --region "$REGION" 2>&1) || true

        local status
        status=$(echo "$result" | jq -r '.Dashboard.Version.Status // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")

        case "$status" in
            CREATION_SUCCESSFUL|UPDATE_SUCCESSFUL)
                echo "    Status: $status"
                return 0
                ;;
            CREATION_FAILED|UPDATE_FAILED)
                echo "    Status: $status"
                local errors
                errors=$(echo "$result" | jq -r '.Dashboard.Version.Errors[]?.Message // empty' 2>/dev/null)
                if [ -n "$errors" ]; then
                    echo "    Errors:"
                    echo "$errors" | sed 's/^/      /'
                fi
                return 1
                ;;
            *)
                attempt=$((attempt + 1))
                if [ $((attempt % 6)) -eq 0 ]; then
                    echo "    Still waiting... ($status, ${attempt}/${POLL_MAX_ATTEMPTS})"
                fi
                sleep "$POLL_INTERVAL"
                ;;
        esac
    done
    echo "    Timed out waiting for dashboard $dashboard_id (last status: $status)"
    return 1
}

# ---------------------------------------------------------------------------
# Dashboards (delete first — they reference analyses/datasets/themes)
# ---------------------------------------------------------------------------
for DASH_FILE in "$OUT_DIR"/financial-dashboard.json; do
    if [ ! -f "$DASH_FILE" ]; then
        continue
    fi
    DASH_ID=$(jq -r '.DashboardId' "$DASH_FILE")
    echo "==> Dashboard: $DASH_ID"
    if aws quicksight describe-dashboard \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --dashboard-id "$DASH_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Deleting existing dashboard..."
        aws quicksight delete-dashboard \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --dashboard-id "$DASH_ID" \
            --region "$REGION" &>/dev/null || true
    fi
done

# ---------------------------------------------------------------------------
# Analyses (delete — they reference datasets and themes)
# ---------------------------------------------------------------------------
for ANALYSIS_FILE in "$OUT_DIR"/financial-analysis.json; do
    if [ ! -f "$ANALYSIS_FILE" ]; then
        continue
    fi
    ANALYSIS_ID=$(jq -r '.AnalysisId' "$ANALYSIS_FILE")
    echo "==> Analysis: $ANALYSIS_ID"
    if aws quicksight describe-analysis \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --analysis-id "$ANALYSIS_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Deleting existing analysis..."
        aws quicksight delete-analysis \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --analysis-id "$ANALYSIS_ID" \
            --region "$REGION" \
            --force-delete-without-recovery &>/dev/null || true
    fi
done

# ---------------------------------------------------------------------------
# Datasets (delete before datasource — they reference it)
# ---------------------------------------------------------------------------
for DS_FILE in "$OUT_DIR"/datasets/*.json; do
    DS_ID=$(jq -r '.DataSetId' "$DS_FILE")
    echo "==> Dataset: $DS_ID"
    if aws quicksight describe-data-set \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --data-set-id "$DS_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Deleting existing dataset..."
        aws quicksight delete-data-set \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --data-set-id "$DS_ID" \
            --region "$REGION" &>/dev/null || true
    fi
done

# ---------------------------------------------------------------------------
# Theme (delete)
# ---------------------------------------------------------------------------
THEME_ID=$(jq -r '.ThemeId' "$OUT_DIR/theme.json")
echo "==> Theme: $THEME_ID"
if aws quicksight describe-theme \
    --aws-account-id "$AWS_ACCOUNT_ID" \
    --theme-id "$THEME_ID" \
    --region "$REGION" &>/dev/null; then
    echo "    Deleting existing theme..."
    aws quicksight delete-theme \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --theme-id "$THEME_ID" \
        --region "$REGION" &>/dev/null || true
fi

# ---------------------------------------------------------------------------
# DataSource (delete — only present when generated via demo apply)
# ---------------------------------------------------------------------------
if [ -f "$OUT_DIR/datasource.json" ]; then
    DS_SOURCE_ID=$(jq -r '.DataSourceId' "$OUT_DIR/datasource.json")
    echo "==> DataSource: $DS_SOURCE_ID"
    if aws quicksight describe-data-source \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --data-source-id "$DS_SOURCE_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Deleting existing datasource..."
        aws quicksight delete-data-source \
            --aws-account-id "$AWS_ACCOUNT_ID" \
            --data-source-id "$DS_SOURCE_ID" \
            --region "$REGION" &>/dev/null || true
    fi
fi

if [ "$DELETE_ONLY" = true ]; then
    echo
    echo "Done. All resources deleted from account $AWS_ACCOUNT_ID in $REGION."
    exit 0
fi

echo
echo "--- Recreating all resources ---"
echo

# ---------------------------------------------------------------------------
# DataSource (create)
# ---------------------------------------------------------------------------
if [ -f "$OUT_DIR/datasource.json" ]; then
    DS_SOURCE_ID=$(jq -r '.DataSourceId' "$OUT_DIR/datasource.json")
    echo "==> Creating DataSource: $DS_SOURCE_ID"
    aws quicksight create-data-source \
        --region "$REGION" \
        --cli-input-json "file://$OUT_DIR/datasource.json"
fi

# ---------------------------------------------------------------------------
# Theme (create)
# ---------------------------------------------------------------------------
echo "==> Creating Theme: $THEME_ID"
aws quicksight create-theme \
    --region "$REGION" \
    --cli-input-json "file://$OUT_DIR/theme.json"

# ---------------------------------------------------------------------------
# Datasets (create)
# ---------------------------------------------------------------------------
for DS_FILE in "$OUT_DIR"/datasets/*.json; do
    DS_ID=$(jq -r '.DataSetId' "$DS_FILE")
    echo "==> Creating Dataset: $DS_ID"
    aws quicksight create-data-set \
        --region "$REGION" \
        --cli-input-json "file://$DS_FILE"
done

# ---------------------------------------------------------------------------
# Analyses (create + wait)
# ---------------------------------------------------------------------------
ANALYSIS_IDS=()
for ANALYSIS_FILE in "$OUT_DIR"/financial-analysis.json; do
    if [ ! -f "$ANALYSIS_FILE" ]; then
        echo "    Skipping $(basename "$ANALYSIS_FILE") (not found)"
        continue
    fi
    ANALYSIS_ID=$(jq -r '.AnalysisId' "$ANALYSIS_FILE")
    echo "==> Creating Analysis: $ANALYSIS_ID"
    aws quicksight create-analysis \
        --region "$REGION" \
        --cli-input-json "file://$ANALYSIS_FILE"
    ANALYSIS_IDS+=("$ANALYSIS_ID")
done

# ---------------------------------------------------------------------------
# Dashboards (create + wait)
# ---------------------------------------------------------------------------
DASHBOARD_IDS=()
for DASH_FILE in "$OUT_DIR"/financial-dashboard.json; do
    if [ ! -f "$DASH_FILE" ]; then
        echo "    Skipping $(basename "$DASH_FILE") (not found)"
        continue
    fi
    DASH_ID=$(jq -r '.DashboardId' "$DASH_FILE")
    echo "==> Creating Dashboard: $DASH_ID"
    aws quicksight create-dashboard \
        --region "$REGION" \
        --cli-input-json "file://$DASH_FILE"
    DASHBOARD_IDS+=("$DASH_ID")
done

# ---------------------------------------------------------------------------
# Wait for all async resources to reach terminal state
# ---------------------------------------------------------------------------
echo
echo "--- Waiting for async resources ---"
echo

FAILURES=0

for AID in "${ANALYSIS_IDS[@]}"; do
    echo "==> Checking Analysis: $AID"
    if ! wait_for_analysis "$AID"; then
        FAILURES=$((FAILURES + 1))
    fi
done

for DID in "${DASHBOARD_IDS[@]}"; do
    echo "==> Checking Dashboard: $DID"
    if ! wait_for_dashboard "$DID"; then
        FAILURES=$((FAILURES + 1))
    fi
done

echo
if [ $FAILURES -gt 0 ]; then
    echo "Done with $FAILURES FAILURE(s). Check errors above."
    exit 1
else
    echo "Done. All resources deployed successfully to account $AWS_ACCOUNT_ID in $REGION."
fi
