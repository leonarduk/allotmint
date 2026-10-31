#!/usr/bin/env bash
# Shared CloudFormation resource lookup for deploy-lambda.yml and
# scripts/bash/pre-deploy-check.sh (mirrored by Get-CfnResourceId in
# scripts/powershell/pre-deploy-check.ps1). Tested offline with a fake `aws`
# in tests/scripts/test_cfn_resource_id.py.

# cfn_resource_id STACK QUERY
#
# Prints the first PhysicalResourceId that QUERY (a --query JMESPath selecting
# PhysicalResourceId values) yields from `aws cloudformation
# list-stack-resources --stack-name STACK`.
#
#   exit 0, prints the id    -- found
#   exit 0, prints nothing   -- the stack does not exist, or nothing matched
#   exit 1, error on stderr  -- the aws call failed for any other reason
#                               (throttling, expired credentials, network)
#
# Callers that fall back when nothing is found must not fall back on exit 1:
# a failed call says nothing about whether the resource exists (#11095).
# "Does not exist" means a ValidationError naming a missing stack (the CLI's
# message is the service's, not localised). Requiring both keeps other
# validation errors failing; if AWS ever rewords it, a missing stack fails
# loudly rather than being silently treated as found-nothing.
#
# QUERY must not end in "| [0]": past 100 resources the CLI applies --query
# per page and prints "<id>\nNone" (#11091). awk keeps the first real value
# and, unlike head -1, reads all input so pipefail never sees a SIGPIPE.
cfn_resource_id() {
  local stack="$1" query="$2" output err_file status=0
  err_file="$(mktemp)"
  # "|| status=$?" keeps a failed call from tripping a caller's set -e here.
  output="$(aws cloudformation list-stack-resources \
    --stack-name "$stack" --query "$query" --output text 2>"$err_file")" || status=$?
  if [ "$status" -ne 0 ]; then
    if grep -q "ValidationError.*does not exist" "$err_file"; then
      rm -f "$err_file"
      return 0
    fi
    echo "aws cloudformation list-stack-resources --stack-name $stack failed (exit $status):" >&2
    cat "$err_file" >&2
    rm -f "$err_file"
    return 1
  fi
  rm -f "$err_file"
  printf '%s\n' "$output" | tr '\t' '\n' | awk 'NF && $0 != "None" && !found {print; found=1}'
}
