#!/usr/bin/env bash
set -euo pipefail

# Strict gate runner for Issue #2581.
# This script performs objective checks and writes a machine-readable summary.

API_BASE="${API_BASE:-http://localhost:8001}"
OWNER="${OWNER:-}"
GROUP_SLUG="${GROUP_SLUG:-}"
RUN_DIR="${RUN_DIR:-artifacts/issue-2581/$(date -u +%Y%m%dT%H%M%SZ)}"
SNAPSHOT_TIME_UTC="${SNAPSHOT_TIME_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
BROKER_SNAPSHOT_TIME_UTC="${BROKER_SNAPSHOT_TIME_UTC:-}"
SYSTEM_FETCH_TIME_UTC="${SYSTEM_FETCH_TIME_UTC:-}"

mkdir -p "$RUN_DIR"

failure_count=0

declare -a failures=()

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_cmd curl
require_cmd jq
require_cmd python3

if [[ -z "$OWNER" || -z "$GROUP_SLUG" ]]; then
  die "OWNER and GROUP_SLUG are required"
fi

record_failure() {
  local code="$1"
  local step="$2"
  local message="$3"
  failure_count=$((failure_count + 1))
  failures+=("$code|$step|$message")
}

write_env_lock() {
  {
    echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "python_version=$(python3 --version 2>&1)"
    echo "api_base=$API_BASE"
    echo "owner=$OWNER"
    echo "group_slug=$GROUP_SLUG"
    echo "snapshot_time_utc=$SNAPSHOT_TIME_UTC"
    echo "broker_snapshot_time_utc=$BROKER_SNAPSHOT_TIME_UTC"
    echo "system_fetch_time_utc=$SYSTEM_FETCH_TIME_UTC"
  } >"$RUN_DIR/environment_lock.txt"

  if command -v docker >/dev/null 2>&1; then
    docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' >"$RUN_DIR/docker_images.txt" || true
  else
    echo "docker not found" >"$RUN_DIR/docker_images.txt"
  fi
}

check_snapshot_window() {
  python3 - "$SNAPSHOT_TIME_UTC" "$BROKER_SNAPSHOT_TIME_UTC" "$SYSTEM_FETCH_TIME_UTC" <<'PY'
import datetime as dt
import sys

snapshot, broker, system = sys.argv[1:4]
if not broker or not system:
    print("MISSING")
    sys.exit(2)

def parse(ts):
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)

s = parse(snapshot)
b = parse(broker)
y = parse(system)

max_drift = dt.timedelta(minutes=5)
if abs(s - b) > max_drift or abs(s - y) > max_drift:
    print("DRIFT")
    sys.exit(1)

print("OK")
PY
}

curl_json() {
  local url="$1"
  local out="$2"
  local status
  status=$(curl -sS -o "$out" -w "%{http_code}" "$url")
  echo "$status" >"$out.status"
  if [[ "$status" != "200" ]]; then
    record_failure "P1" "http" "Non-200 response from $url: $status"
  fi
}

check_health_latency() {
  local out="$RUN_DIR/backend_health.json"
  local latency
  latency=$(curl -sS -o "$out" -w "%{time_total}" "$API_BASE/health" || echo "999")
  echo "$latency" >"$RUN_DIR/backend_health.latency"
  python3 - "$latency" <<'PY'
import sys
lat = float(sys.argv[1])
if lat >= 2.0:
    sys.exit(1)
PY
}

check_no_null_or_negative_weights() {
  local json_file="$1"
  local label="$2"
  python3 - "$json_file" "$label" <<'PY'
import json, math, sys

path, label = sys.argv[1:3]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

weights = []

def walk(v):
    if isinstance(v, dict):
        for k, vv in v.items():
            if vv is None:
                raise ValueError(f"{label}: null value at key {k}")
            if isinstance(vv, (int, float)) and not isinstance(vv, bool):
                if not math.isfinite(vv):
                    raise ValueError(f"{label}: non-finite number at key {k}")
                if 'weight' in k.lower() or k in ('percentage', 'percent', 'value_pct'):
                    weights.append(float(vv))
            walk(vv)
    elif isinstance(v, list):
        for i in v:
            walk(i)

walk(data)
if any(w < 0 for w in weights):
    raise ValueError(f"{label}: negative weights found")
if weights:
    total = sum(weights)
    if abs(total - 100.0) > 1.0:
        raise ValueError(f"{label}: weight sum {total:.4f} outside 100±1")
PY
}

check_var_structure() {
  local json_file="$1"
  python3 - "$json_file" <<'PY'
import json, math, re, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

blob = json.dumps(data)
if re.search(r'NaN|null', blob):
    raise ValueError('VaR payload contains NaN/null')

value = None
for key in ('var', 'var_pct', 'value_at_risk'):
    if isinstance(data, dict) and key in data and isinstance(data[key], (int, float)):
        value = float(data[key])
        break

if value is None:
    raise ValueError('VaR numeric value not found')
if not math.isfinite(value) or value <= 0:
    raise ValueError('VaR must be finite and > 0')
PY
}

write_summary() {
  local verdict="PASS"
  if (( failure_count > 0 )); then
    verdict="FAIL"
  fi

  {
    echo "{"
    echo "  \"timestamp_utc\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"run_dir\": \"$RUN_DIR\","
    echo "  \"verdict\": \"$verdict\","
    echo "  \"failure_count\": $failure_count,"
    echo "  \"failures\": ["
    local first=1
    for f in "${failures[@]}"; do
      IFS='|' read -r code step message <<<"$f"
      if [[ $first -eq 0 ]]; then
        echo ","
      fi
      first=0
      printf '    {"severity":"%s","step":"%s","message":%s}' "$code" "$step" "$(jq -Rn --arg m "$message" '$m')"
    done
    echo
    echo "  ]"
    echo "}"
  } >"$RUN_DIR/summary.json"

  echo "Wrote summary to $RUN_DIR/summary.json"
  [[ "$verdict" == "PASS" ]]
}

main() {
  write_env_lock

  if ! check_snapshot_window >"$RUN_DIR/snapshot_window_check.txt" 2>&1; then
    reason=$(cat "$RUN_DIR/snapshot_window_check.txt" 2>/dev/null || echo "unknown")
    if [[ "$reason" == "MISSING" ]]; then
      record_failure "P2" "global" "Missing broker/system snapshot timestamp"
    else
      record_failure "P1" "global" "Snapshot drift exceeds ±5 minutes"
    fi
  fi

  # Step 1
  if ! check_health_latency; then
    record_failure "P1" "step1" "Backend /health latency >= 2s"
  fi

  # Step 2
  curl_json "$API_BASE/portfolio/$OWNER" "$RUN_DIR/portfolio_response.json"

  # Step 3
  curl_json "$API_BASE/portfolio/$OWNER/sectors" "$RUN_DIR/sectors.json"
  curl_json "$API_BASE/portfolio-group/$GROUP_SLUG/regions" "$RUN_DIR/regions.json"
  if ! check_no_null_or_negative_weights "$RUN_DIR/sectors.json" "sectors"; then
    record_failure "P1" "step3" "Sector structure check failed"
  fi
  if ! check_no_null_or_negative_weights "$RUN_DIR/regions.json" "regions"; then
    record_failure "P1" "step3" "Region structure check failed"
  fi

  # Step 4
  curl_json "$API_BASE/var/$OWNER" "$RUN_DIR/var.json"
  if ! check_var_structure "$RUN_DIR/var.json"; then
    record_failure "P1" "step4" "VaR structural check failed"
  fi

  # Step 5
  code=$(curl -sS -o "$RUN_DIR/audit_report.pdf" -w "%{http_code}" "$API_BASE/reports/$OWNER/audit-report?format=pdf")
  echo "$code" >"$RUN_DIR/audit_report.pdf.status"
  if [[ "$code" != "200" ]]; then
    record_failure "P1" "step5" "Audit PDF generation failed with status $code"
  fi

  # Step 6
  demo_code=$(curl -sS -o "$RUN_DIR/demo_report.pdf" -w "%{http_code}" "$API_BASE/reports/demo-owner/audit-report?format=pdf&watermark=SAMPLE")
  echo "$demo_code" >"$RUN_DIR/demo_report.pdf.status"
  if [[ "$demo_code" != "200" ]]; then
    record_failure "P1" "step6" "Demo PDF generation failed with status $demo_code"
  fi

  write_summary
}

main "$@"
