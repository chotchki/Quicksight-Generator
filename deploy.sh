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
# This script is idempotent — it uses create-* on first run and
# update-* on subsequent runs.

set -euo pipefail

OUT_DIR="${1:-out}"
AWS_ACCOUNT_ID=$(jq -r '.AwsAccountId' "$OUT_DIR/theme.json")
REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

echo "Deploying QuickSight resources from $OUT_DIR"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Region:  $REGION"
echo

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
THEME_ID=$(jq -r '.ThemeId' "$OUT_DIR/theme.json")
echo "==> Theme: $THEME_ID"
if aws quicksight describe-theme \
    --aws-account-id "$AWS_ACCOUNT_ID" \
    --theme-id "$THEME_ID" \
    --region "$REGION" &>/dev/null; then
    echo "    Updating existing theme..."
    aws quicksight update-theme \
        --region "$REGION" \
        --cli-input-json "file://$OUT_DIR/theme.json"
else
    echo "    Creating new theme..."
    aws quicksight create-theme \
        --region "$REGION" \
        --cli-input-json "file://$OUT_DIR/theme.json"
fi

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
for DS_FILE in "$OUT_DIR"/datasets/*.json; do
    DS_ID=$(jq -r '.DataSetId' "$DS_FILE")
    echo "==> Dataset: $DS_ID"
    if aws quicksight describe-data-set \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --data-set-id "$DS_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Updating existing dataset..."
        aws quicksight update-data-set \
            --region "$REGION" \
            --cli-input-json "file://$DS_FILE"
    else
        echo "    Creating new dataset..."
        aws quicksight create-data-set \
            --region "$REGION" \
            --cli-input-json "file://$DS_FILE"
    fi
done

# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------
for ANALYSIS_FILE in "$OUT_DIR"/financial-analysis.json "$OUT_DIR"/recon-analysis.json; do
    if [ ! -f "$ANALYSIS_FILE" ]; then
        echo "    Skipping $(basename "$ANALYSIS_FILE") (not found)"
        continue
    fi
    ANALYSIS_ID=$(jq -r '.AnalysisId' "$ANALYSIS_FILE")
    echo "==> Analysis: $ANALYSIS_ID"
    if aws quicksight describe-analysis \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --analysis-id "$ANALYSIS_ID" \
        --region "$REGION" &>/dev/null; then
        echo "    Updating existing analysis..."
        aws quicksight update-analysis \
            --region "$REGION" \
            --cli-input-json "file://$ANALYSIS_FILE"
    else
        echo "    Creating new analysis..."
        aws quicksight create-analysis \
            --region "$REGION" \
            --cli-input-json "file://$ANALYSIS_FILE"
    fi
done

echo
echo "Done. Resources deployed to account $AWS_ACCOUNT_ID in $REGION."
