#!/usr/bin/env bash
set -euo pipefail

# Strict gate runner for Issue #2581.
# This script performs objective checks and writes durable evidence artifacts
# suitable for attaching to the GitHub issue.

API_BASE="${API_BASE:-http://localhost:8001}"
OWNER="${OWNER:-}"
GROUP_SLUG="${GROUP_SLUG:-}"
RUN_DIR="${RUN_DIR:-artifacts/issue-2581/$(date -u +%Y%m%dT%H%M%SZ)}"
SNAPSHOT_TIME_UTC="${SNAPSHOT_TIME_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
BROKER_SNAPSHOT_TIME_UTC="${BROKER_SNAPSHOT_TIME_UTC:-}"
SYSTEM_FETCH_TIME_UTC="${SYSTEM_FETCH_TIME_UTC:-}"

mkdir -p "$RUN_DIR"

failure_count=0
run_verdict="PASS"

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

# Fetch a URL, save the body to $out, record HTTP status.
# On transport failure (curl non-zero exit) the function records a P1 failure
# and continues — it does NOT abort the whole runner so that summary.json
# is always produced.
curl_json() {
  local url="$1"
  local out="$2"
  local status
  # Run curl in a subshell so its exit code does not propagate through set -e.
  if ! status=$(curl -sS -o "$out" -w "%{http_code}" "$url" 2>"$out.stderr"); then
    local curl_err
    curl_err=$(cat "$out.stderr" 2>/dev/null || echo "unknown curl error")
    record_failure "P1" "http" "curl transport error for $url: $curl_err"
    echo "000" >"$out.status"
    return
  fi
  echo "$status" >"$out.status"
  if [[ "$status" != "200" ]]; then
    record_failure "P1" "http" "Non-200 response from $url: $status"
  fi
}

check_health_latency() {
  local out="$RUN_DIR/backend_health.json"
  local status latency combined
  # Capture both status and latency; guard against transport errors.
  if ! combined=$(curl -sS -o "$out" -w "%{http_code} %{time_total}" "$API_BASE/health" 2>"$RUN_DIR/backend_health.stderr"); then
    record_failure "P1" "step1" "Backend /health unreachable: $(cat "$RUN_DIR/backend_health.stderr" 2>/dev/null)"
    echo "000 999" >"$RUN_DIR/backend_health.timing"
    return 1
  fi
  echo "$combined" >"$RUN_DIR/backend_health.timing"
  # combined is "<http_status> <time_total>" e.g. "200 0.123456"
  status=$(echo "$combined" | awk '{print $1}')
  latency=$(echo "$combined" | awk '{print $2}')
  if [[ "$status" != "200" ]]; then
    record_failure "P1" "step1" "Backend /health returned HTTP $status"
    return 1
  fi
  python3 - "$latency" <<'PY'
import sys
try:
    lat = float(sys.argv[1])
except ValueError:
    print(f"Could not parse latency: {sys.argv[1]}", file=sys.stderr)
    sys.exit(1)
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

def _coerce_numeric(candidate):
    if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
        return float(candidate)
    return None

if isinstance(data, dict):
    for key in ('var', 'var_pct', 'value_at_risk'):
        numeric = _coerce_numeric(data.get(key))
        if numeric is not None:
            value = numeric
            break

    if value is None and isinstance(data.get('var'), dict):
        nested_var = data['var']
        for horizon in ('1d', '10d'):
            numeric = _coerce_numeric(nested_var.get(horizon))
            if numeric is not None:
                value = numeric
                break

        if value is None:
            for nested_key, nested_value in nested_var.items():
                if nested_key in ('window_days', 'confidence'):
                    continue
                numeric = _coerce_numeric(nested_value)
                if numeric is not None:
                    value = numeric
                    break

if value is None:
    raise ValueError('VaR numeric value not found')
if not math.isfinite(value) or value <= 0:
    raise ValueError('VaR must be finite and > 0')
PY
}

check_audit_report_sections() {
  local json_file="$1"
  python3 - "$json_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)

sections = data.get("sections")
if not isinstance(sections, list):
    raise ValueError("Report JSON missing 'sections' array")

titles = []
for section in sections:
    if not isinstance(section, dict):
        raise ValueError("Report JSON contains non-object section entry")
    title = section.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Report JSON section missing non-empty title")
    titles.append(title)

required = [
    "Portfolio overview",
    "Sector allocation",
    "Region allocation",
    "Top holdings concentration",
]
for index, expected in enumerate(required):
    if index >= len(titles) or titles[index] != expected:
        raise ValueError(
            f"Section {index + 1} must be '{expected}', got: {titles[index] if index < len(titles) else 'missing'}"
        )

allowed_optional = {"Portfolio risk", "Key Findings"}
extras = titles[len(required):]
for title in extras:
    if title not in allowed_optional:
        raise ValueError(f"Unexpected audit-report section title: {title}")

if len(titles) < 4 or len(titles) > 6:
    raise ValueError(f"Section count must be between 4 and 6 inclusive, got {len(titles)}")

if "Key Findings" in titles and titles[-1] != "Key Findings":
    raise ValueError("Key Findings must be the last section when present")

if "Portfolio risk" in titles and titles.index("Portfolio risk") != 4:
    raise ValueError("Portfolio risk must be section 5 when present")
PY
}

write_summary() {
  run_verdict="PASS"
  if (( failure_count > 0 )); then
    run_verdict="FAIL"
  fi

  {
    echo "{"
    echo "  \"timestamp_utc\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"run_dir\": \"$RUN_DIR\","
    echo "  \"verdict\": \"$run_verdict\","
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
}

write_evidence_manifest() {
  cat >"$RUN_DIR/evidence_manifest.txt" <<EOF
Issue: #2581
Run timestamp (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)
Run directory: $RUN_DIR

Required issue attachments
- summary.json
- summary_for_issue.md
- environment_lock.txt
- evidence_manifest.txt
- audit_report.pdf
- demo_report.pdf

Required local durable evidence
- backend_health.json
- backend_health.timing
- frontend_screenshot.png
- startup_log.txt
- portfolio_response.json
- broker_snapshot.txt
- sectors.json
- regions.json
- var.json
- docker_images.txt
- transport/check logs (*.stderr, *.status, *.check.log)
EOF
}

write_issue_summary_markdown() {
  local failure_lines=""

  if (( failure_count > 0 )); then
    for f in "${failures[@]}"; do
      IFS='|' read -r code step message <<<"$f"
      failure_lines+="- [$code] **$step**: $message"$'\n'
    done
  else
    failure_lines="- None"$'\n'
  fi

  cat >"$RUN_DIR/summary_for_issue.md" <<EOF
## Issue #2581 strict run summary

- **Verdict:** $run_verdict
- **Run timestamp (UTC):** $(date -u +%Y-%m-%dT%H:%M:%SZ)
- **Run directory:** \`$RUN_DIR\`
- **Environment lock:** \`$RUN_DIR/environment_lock.txt\`
- **Machine summary:** \`$RUN_DIR/summary.json\`
- **Evidence manifest:** \`$RUN_DIR/evidence_manifest.txt\`

### Failures
$failure_lines
### Required issue attachments
- \`summary.json\`
- \`summary_for_issue.md\`
- \`environment_lock.txt\`
- \`evidence_manifest.txt\`
- \`audit_report.pdf\`
- \`demo_report.pdf\`

### Local-only (retain in run directory; attach when needed for review)
- \`backend_health.json\`
- \`backend_health.timing\`
- \`frontend_screenshot.png\`
- \`startup_log.txt\`
- \`portfolio_response.json\`
- \`broker_snapshot.txt\`
- \`sectors.json\`
- \`regions.json\`
- \`var.json\`
- transport/check logs (\`*.stderr\`, \`*.check.log\`, \`*.status\`)
EOF
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
  if [[ -f "$RUN_DIR/sectors.json" ]] && ! check_no_null_or_negative_weights "$RUN_DIR/sectors.json" "sectors" 2>>"$RUN_DIR/sectors.check.log"; then
    record_failure "P1" "step3" "Sector structure check failed"
  fi
  if [[ -f "$RUN_DIR/regions.json" ]] && ! check_no_null_or_negative_weights "$RUN_DIR/regions.json" "regions" 2>>"$RUN_DIR/regions.check.log"; then
    record_failure "P1" "step3" "Region structure check failed"
  fi

  # Step 4
  curl_json "$API_BASE/var/$OWNER" "$RUN_DIR/var.json"
  if [[ -f "$RUN_DIR/var.json" ]] && ! check_var_structure "$RUN_DIR/var.json" 2>>"$RUN_DIR/var.check.log"; then
    record_failure "P1" "step4" "VaR structural check failed"
  fi

  # Step 5
  local code
  code=$(curl -sS -o "$RUN_DIR/audit_report.pdf" -w "%{http_code}" "$API_BASE/reports/$OWNER/audit-report?format=pdf" 2>"$RUN_DIR/audit_report.stderr" || echo "000")
  echo "$code" >"$RUN_DIR/audit_report.pdf.status"
  if [[ "$code" != "200" ]]; then
    record_failure "P1" "step5" "Audit PDF generation failed with status $code"
  fi
  curl_json "$API_BASE/reports/$OWNER/audit-report?format=json" "$RUN_DIR/audit_report.json"
  if [[ -f "$RUN_DIR/audit_report.json" ]] && ! check_audit_report_sections "$RUN_DIR/audit_report.json" 2>>"$RUN_DIR/audit_report.check.log"; then
    record_failure "P1" "step5" "Audit report section contract check failed"
  fi

  # Step 6
  local demo_code
  demo_code=$(curl -sS -o "$RUN_DIR/demo_report.pdf" -w "%{http_code}" "$API_BASE/reports/demo-owner/audit-report?format=pdf&watermark=SAMPLE" 2>"$RUN_DIR/demo_report.stderr" || echo "000")
  echo "$demo_code" >"$RUN_DIR/demo_report.pdf.status"
  if [[ "$demo_code" != "200" ]]; then
    record_failure "P1" "step6" "Demo PDF generation failed with status $demo_code"
  fi

  write_summary
  write_evidence_manifest
  write_issue_summary_markdown
  [[ "$run_verdict" == "PASS" ]]
}

main "$@"
