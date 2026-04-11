#!/usr/bin/env bash
#
# Deploy generated QuickSight resources using the AWS CLI.
#
# Usage:
#   1. Generate JSON:  python -m quicksight_gen generate -c config.yaml
#   2. Deploy:         ./deploy.sh [output-dir]
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - QuickSight Enterprise edition enabled in the target account
#
# This script is idempotent — it deletes existing resources and recreates
# them on each run to avoid update-command parameter mismatches.

set -euo pipefail

OUT_DIR="${1:-out}"
AWS_ACCOUNT_ID=$(jq -r '.AwsAccountId' "$OUT_DIR/theme.json")
REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

echo "Deploying QuickSight resources from $OUT_DIR"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Region:  $REGION"
echo

# ---------------------------------------------------------------------------
# Dashboards (delete first — they reference analyses/datasets/themes)
# ---------------------------------------------------------------------------
for DASH_FILE in "$OUT_DIR"/financial-dashboard.json "$OUT_DIR"/recon-dashboard.json; do
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
for ANALYSIS_FILE in "$OUT_DIR"/financial-analysis.json "$OUT_DIR"/recon-analysis.json; do
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
# Analyses (create)
# ---------------------------------------------------------------------------
for ANALYSIS_FILE in "$OUT_DIR"/financial-analysis.json "$OUT_DIR"/recon-analysis.json; do
    if [ ! -f "$ANALYSIS_FILE" ]; then
        echo "    Skipping $(basename "$ANALYSIS_FILE") (not found)"
        continue
    fi
    ANALYSIS_ID=$(jq -r '.AnalysisId' "$ANALYSIS_FILE")
    echo "==> Creating Analysis: $ANALYSIS_ID"
    aws quicksight create-analysis \
        --region "$REGION" \
        --cli-input-json "file://$ANALYSIS_FILE"
done

# ---------------------------------------------------------------------------
# Dashboards (create — after analyses)
# ---------------------------------------------------------------------------
DASH_URLS=()
for DASH_FILE in "$OUT_DIR"/financial-dashboard.json "$OUT_DIR"/recon-dashboard.json; do
    if [ ! -f "$DASH_FILE" ]; then
        echo "    Skipping $(basename "$DASH_FILE") (not found)"
        continue
    fi
    DASH_ID=$(jq -r '.DashboardId' "$DASH_FILE")
    DASH_NAME=$(jq -r '.Name' "$DASH_FILE")
    echo "==> Creating Dashboard: $DASH_ID"
    CREATE_RESULT=$(aws quicksight create-dashboard \
        --region "$REGION" \
        --cli-input-json "file://$DASH_FILE")
    DASH_URL=$(echo "$CREATE_RESULT" | jq -r '.Url // empty')
    if [ -n "$DASH_URL" ]; then
        DASH_URLS+=("  $DASH_NAME: $DASH_URL")
    fi
done

echo
echo "Done. Resources deployed to account $AWS_ACCOUNT_ID in $REGION."

if [ ${#DASH_URLS[@]} -gt 0 ]; then
    echo
    echo "Dashboard links:"
    for URL_LINE in "${DASH_URLS[@]}"; do
        echo "$URL_LINE"
    done
fi
