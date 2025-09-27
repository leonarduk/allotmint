#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: deploy-to-aws.sh -b <bucket> [-d <distribution-id>] [-r <region>] [-p <invalidate-path>] [-n]

Options:
  -b   S3 bucket name (required)
  -d   CloudFront distribution ID (optional)
  -r   AWS region (defaults to $AWS_REGION or eu-west-2)
  -p   CloudFront invalidate path (default: /*)
  -n   Dry run (builds but prints AWS commands instead of executing)

Environment variables (alternative to flags):
  S3_BUCKET, CLOUDFRONT_DISTRIBUTION_ID, AWS_REGION
EOF
}

bucket="${S3_BUCKET:-}"
dist_id="${CLOUDFRONT_DISTRIBUTION_ID:-}"
region="${AWS_REGION:-}"
invalidate_path="/*"
dry_run=false

while getopts ":b:d:r:p:nh" opt; do
  case "$opt" in
    b) bucket="$OPTARG" ;;
    d) dist_id="$OPTARG" ;;
    r) region="$OPTARG" ;;
    p) invalidate_path="$OPTARG" ;;
    n) dry_run=true ;;
    h) usage; exit 0 ;;
    :) echo "Error: -$OPTARG requires an argument" >&2; usage; exit 2 ;;
    \?) echo "Error: invalid option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$bucket" ]]; then
  echo "Error: S3 bucket is required (-b or S3_BUCKET)" >&2
  usage
  exit 2
fi

if [[ -z "$region" ]]; then
  region="eu-west-2"
fi

echo "\n=== Validating environment ==="
if [[ ! -f package.json ]]; then
  echo "Run this script from the frontend repo root (package.json not found)" >&2
  exit 1
fi

echo "AWS Region: $region"
echo "S3 Bucket: s3://$bucket"
if [[ -n "$dist_id" ]]; then
  echo "CloudFront Distribution: $dist_id"
fi

has_aws=true
if ! command -v aws >/dev/null 2>&1; then
  has_aws=false
  if [[ "$dry_run" != true ]]; then
    echo "Warning: aws CLI not found on PATH. Falling back to dry run." >&2
    dry_run=true
  fi
fi

echo "\n=== Building frontend ==="

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  VITE_GIT_COMMIT_DEFAULT="$(git rev-parse HEAD)"
  VITE_GIT_BRANCH_DEFAULT="$(git rev-parse --abbrev-ref HEAD)"
  : "${VITE_GIT_COMMIT:=$VITE_GIT_COMMIT_DEFAULT}"
  : "${VITE_GIT_BRANCH:=$VITE_GIT_BRANCH_DEFAULT}"
fi

export VITE_GIT_COMMIT="${VITE_GIT_COMMIT:-}"
export VITE_GIT_BRANCH="${VITE_GIT_BRANCH:-}"

npm run build

if [[ ! -d dist ]]; then
  echo "Build output folder ./dist not found" >&2
  exit 1
fi

echo "\n=== Syncing to S3 ==="
sync_cmd=(aws s3 sync dist "s3://$bucket/" --delete --region "$region" --only-show-errors --cache-control "public, max-age=300")
if [[ "$dry_run" == true ]]; then
  echo "DRY RUN: ${sync_cmd[*]}"
else
  if [[ "$has_aws" == true ]]; then
    "${sync_cmd[@]}"
  else
    echo "aws CLI not available; cannot sync" >&2
    exit 1
  fi
fi

if [[ -n "$dist_id" ]]; then
  echo "\n=== Creating CloudFront invalidation ==="
  inv_cmd=(aws cloudfront create-invalidation --distribution-id "$dist_id" --paths "$invalidate_path")
  if [[ "$dry_run" == true ]]; then
    echo "DRY RUN: ${inv_cmd[*]}"
  else
    if [[ "$has_aws" == true ]]; then
      "${inv_cmd[@]}" >/dev/null
    else
      echo "aws CLI not available; cannot invalidate" >&2
      exit 1
    fi
  fi
fi

echo "\n=== Done ==="
if [[ "$dry_run" == true ]]; then
  echo "Dry run complete. No changes were made."
fi

