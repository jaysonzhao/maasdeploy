#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

for dependency in oc curl jq; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        echo "Required command not found: $dependency" >&2
        exit 1
    fi
done

if ! oc whoami >/dev/null 2>&1; then
    echo "Log in to the target OpenShift cluster first with oc login." >&2
    exit 1
fi

MODEL_REF="${MAAS_MODEL_REF:-gpt-oss-20b}"
MODEL_ID="${MAAS_MODEL:-}"
FREE_SUBSCRIPTION="${MAAS_FREE_SUBSCRIPTION:-${MODEL_REF}-free}"
PREMIUM_SUBSCRIPTION="${MAAS_PREMIUM_SUBSCRIPTION:-${MODEL_REF}-premium}"
DURATION_SECONDS="${MAAS_DURATION_SECONDS:-180}"
API_KEY_TTL="${MAAS_API_KEY_TTL:-2160h}"
INTERVAL_SECONDS="${MAAS_INTERVAL_SECONDS:-0.5}"
MAX_TOKENS="${MAAS_MAX_TOKENS:-20}"
REQUEST_TIMEOUT_SECONDS="${MAAS_REQUEST_TIMEOUT_SECONDS:-2}"
CONCURRENCY="${MAAS_CONCURRENCY:-8}"
VERIFY_TLS="${MAAS_VERIFY_TLS:-true}"
CURL_OPTIONS=(-sS)
case "$VERIFY_TLS" in
    false|False|FALSE|0|no|No|NO) CURL_OPTIONS+=(-k) ;;
esac
if [[ ! "$DURATION_SECONDS" =~ ^[1-9][0-9]*$ || "$DURATION_SECONDS" -gt 240 ]]; then
    echo "MAAS_DURATION_SECONDS must be an integer from 1 to 240 seconds." >&2
    exit 2
fi
if [[ ! "$MAX_TOKENS" =~ ^[1-9][0-9]*$ || "$MAX_TOKENS" -gt 4096 ]]; then
    echo "MAAS_MAX_TOKENS must be an integer from 1 to 4096." >&2
    exit 2
fi
if [[ ! "$REQUEST_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ || "$REQUEST_TIMEOUT_SECONDS" -gt 300 ]]; then
    echo "MAAS_REQUEST_TIMEOUT_SECONDS must be an integer from 1 to 300." >&2
    exit 2
fi
if [[ ! "$CONCURRENCY" =~ ^[1-9][0-9]*$ || "$CONCURRENCY" -gt 8 ]]; then
    echo "MAAS_CONCURRENCY must be an integer from 1 to 8." >&2
    exit 2
fi
if [[ ! "$INTERVAL_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ || "$INTERVAL_SECONDS" == "0" || "$INTERVAL_SECONDS" == "0.0" ]]; then
    echo "MAAS_INTERVAL_SECONDS must be a positive number." >&2
    exit 2
fi

if [[ ! "$MODEL_REF" =~ ^[a-zA-Z0-9._/-]+$ || ( -n "$MODEL_ID" && ! "$MODEL_ID" =~ ^[a-zA-Z0-9._/-]+$ ) ]]; then
    echo "MAAS_MODEL or MAAS_MODEL_REF contains unsupported characters." >&2
    exit 2
fi

CLUSTER_DOMAIN="$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')"
if [[ -z "$CLUSTER_DOMAIN" ]]; then
    echo "Could not discover the cluster ingress domain." >&2
    exit 1
fi
MAAS_BASE_URL="${MAAS_BASE_URL:-https://maas.${CLUSTER_DOMAIN}}"
ADMIN_TOKEN="$(oc whoami -t)"

MAAS_MODEL_PHASE="$(oc get maasmodelref "$MODEL_REF" -n llm -o jsonpath='{.status.phase}' 2>/dev/null || true)"
if [[ "$MAAS_MODEL_PHASE" != "Ready" ]]; then
    echo "MaaSModelRef '$MODEL_REF' is not Ready (phase: ${MAAS_MODEL_PHASE:-unknown}). Deploy the model first." >&2
    exit 1
fi

oc apply -f - >/dev/null <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: maas-load-test
  labels:
    app.kubernetes.io/part-of: maas-load-test
YAML
if oc get secret maas-loadtest-keys -n maas-load-test >/dev/null 2>&1; then
    echo "A prior maas-loadtest-keys Secret exists. Run scripts/cleanup-maas-loadtest.sh before replacing the CronJob credentials." >&2
    exit 1
fi

umask 077
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/maas-loadtest.XXXXXX")"
FREE_KEY_CREATED=""
PREMIUM_KEY_CREATED=""
cleanup_on_error() {
    local api_key_id="$1"
    if [[ -n "$api_key_id" ]]; then
        curl "${CURL_OPTIONS[@]}" -o /dev/null -X DELETE \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" \
            "${MAAS_BASE_URL}/maas-api/v1/api-keys/${api_key_id}" || true
    fi
}
on_exit() {
    local failed=0
    if [[ -n "$FREE_KEY_CREATED" ]]; then
        cleanup_on_error "$FREE_KEY_CREATED"
        failed=1
    fi
    if [[ -n "$PREMIUM_KEY_CREATED" ]]; then
        cleanup_on_error "$PREMIUM_KEY_CREATED"
        failed=1
    fi
    if [[ "$failed" -eq 1 ]]; then
        oc delete namespace maas-load-test --wait=false >/dev/null 2>&1 || true
    fi
    rm -rf "$WORK_DIR"
}
trap on_exit EXIT

create_key() {
    local name="$1"
    local subscription="$2"
    local response_file="$3"
    local key_file="$4"
    local id_file="$5"
    local body_file="$6"
    local status
    jq -cn --arg name "$name" --arg subscription "$subscription" --arg expires_in "$API_KEY_TTL" \
        '{name:$name,description:"Recurring MaaS rate-limit load demo",subscription:$subscription,expiresIn:$expires_in}' \
        > "$body_file"
    status="$(curl "${CURL_OPTIONS[@]}" -o "$response_file" -w '%{http_code}' \
        -X POST "${MAAS_BASE_URL}/maas-api/v1/api-keys" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H 'Content-Type: application/json' \
        --data-binary "@${body_file}")" || status="000"
    if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
        echo "MaaS API-key creation failed for subscription '$subscription' (HTTP ${status})." >&2
        return 1
    fi
    jq -er '.key | strings | select(length > 0)' "$response_file" | tr -d '\r\n' > "$key_file" || {
        echo "MaaS API did not return an API key for '$subscription'." >&2
        return 1
    }
    jq -er '.id | strings | select(length > 0)' "$response_file" | tr -d '\r\n' > "$id_file" || {
        echo "MaaS API did not return an API-key ID for '$subscription'." >&2
        return 1
    }
}

echo "Creating regular API keys for '${FREE_SUBSCRIPTION}' and '${PREMIUM_SUBSCRIPTION}' (expires in ${API_KEY_TTL})..."
create_key "maas-load-free-$(date +%s)" "$FREE_SUBSCRIPTION" \
    "$WORK_DIR/free-response.json" "$WORK_DIR/FREE_API_KEY" "$WORK_DIR/FREE_API_KEY_ID" "$WORK_DIR/free-request.json"
FREE_KEY_CREATED="$(cat "$WORK_DIR/FREE_API_KEY_ID")"
create_key "maas-load-premium-$(date +%s)" "$PREMIUM_SUBSCRIPTION" \
    "$WORK_DIR/premium-response.json" "$WORK_DIR/PREMIUM_API_KEY" "$WORK_DIR/PREMIUM_API_KEY_ID" "$WORK_DIR/premium-request.json"
PREMIUM_KEY_CREATED="$(cat "$WORK_DIR/PREMIUM_API_KEY_ID")"

oc create secret generic maas-loadtest-keys -n maas-load-test \
    --from-file=FREE_API_KEY="$WORK_DIR/FREE_API_KEY" \
    --from-file=FREE_API_KEY_ID="$WORK_DIR/FREE_API_KEY_ID" \
    --from-file=PREMIUM_API_KEY="$WORK_DIR/PREMIUM_API_KEY" \
    --from-file=PREMIUM_API_KEY_ID="$WORK_DIR/PREMIUM_API_KEY_ID" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null

oc create configmap maas-loadtest-settings -n maas-load-test \
    --from-literal=MAAS_BASE_URL="$MAAS_BASE_URL" \
    --from-literal=MAAS_MODEL="$MODEL_ID" \
    --from-literal=MAAS_MODEL_REF="$MODEL_REF" \
    --from-literal=MAAS_DURATION_SECONDS="$DURATION_SECONDS" \
    --from-literal=MAAS_INTERVAL_SECONDS="$INTERVAL_SECONDS" \
    --from-literal=MAAS_MAX_TOKENS="$MAX_TOKENS" \
    --from-literal=MAAS_REQUEST_TIMEOUT_SECONDS="$REQUEST_TIMEOUT_SECONDS" \
    --from-literal=MAAS_CONCURRENCY="$CONCURRENCY" \
    --from-literal=MAAS_VERIFY_TLS="$VERIFY_TLS" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null

if ! oc apply -k "${REPO_ROOT}/manifests/09-load-test" >/dev/null; then
    echo "Could not apply the rate-limit Job; revoking its temporary API keys." >&2
    exit 1
fi
FREE_KEY_CREATED=""
PREMIUM_KEY_CREATED=""
echo "Configured CronJob maas-rate-limit-demo in namespace maas-load-test (every 20 minutes)."
echo "Each run sends up to ${DURATION_SECONDS}s of load to both subscriptions."
echo "Watch free-tier logs with: oc logs -f -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c free-tier"
echo "Watch premium logs with:   oc logs -f -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c premium-tier"
echo "Remove it with:  scripts/cleanup-maas-loadtest.sh"
