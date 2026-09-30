#!/usr/bin/env bash
set -euo pipefail

# Required: MAAS_BASE_URL, MAAS_FREE_API_KEY, MAAS_PREMIUM_API_KEY.
# Optional: MAAS_MODEL, MAAS_REQUESTS_PER_TIER, MAAS_MAX_TOKENS,
#           MAAS_PROMPT, MAAS_INSECURE_TLS=true.
: "${MAAS_BASE_URL:?Set MAAS_BASE_URL to the MaaS gateway URL}"
: "${MAAS_FREE_API_KEY:?Set MAAS_FREE_API_KEY in the environment}"
: "${MAAS_PREMIUM_API_KEY:?Set MAAS_PREMIUM_API_KEY in the environment}"

for dependency in curl jq; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        echo "Required command not found: $dependency" >&2
        exit 1
    fi
done

REQUESTS_PER_TIER="${MAAS_REQUESTS_PER_TIER:-16}"
MAX_TOKENS="${MAAS_MAX_TOKENS:-50}"
PROMPT="${MAAS_PROMPT:-Hello, write me a very long essay about the history of computing}"

if [[ ! "$REQUESTS_PER_TIER" =~ ^[1-9][0-9]*$ ]]; then
    echo "MAAS_REQUESTS_PER_TIER must be a positive integer" >&2
    exit 2
fi
if [[ ! "$MAX_TOKENS" =~ ^[1-9][0-9]*$ ]]; then
    echo "MAAS_MAX_TOKENS must be a positive integer" >&2
    exit 2
fi

BASE_URL="${MAAS_BASE_URL%/}"
MODELS_URL="${BASE_URL}/maas-api/v1/models"
COMPLETION_URL="${BASE_URL}/v1/chat/completions"
MODEL_NAME="${MAAS_MODEL:-}"
CURL_OPTIONS=(--silent --show-error --connect-timeout 10 --max-time 60)
if [[ "${MAAS_INSECURE_TLS:-false}" == "true" ]]; then
    CURL_OPTIONS+=(--insecure)
fi

if [[ -z "$MODEL_NAME" ]]; then
    echo "Fetching available model..."
    MODELS_RESPONSE=$(curl "${CURL_OPTIONS[@]}" \
        -H "Authorization: Bearer ${MAAS_PREMIUM_API_KEY}" \
        "$MODELS_URL") || {
        echo "Could not fetch models; set MAAS_MODEL to specify one directly" >&2
        exit 1
    }
    MODEL_NAME=$(printf '%s' "$MODELS_RESPONSE" | jq -er '.data[0].id // empty') || {
        echo "No model was returned; set MAAS_MODEL to specify one directly" >&2
        exit 1
    }
    unset MODELS_RESPONSE
fi

PAYLOAD=$(jq -cn \
    --arg model "$MODEL_NAME" \
    --arg prompt "$PROMPT" \
    --argjson max_tokens "$MAX_TOKENS" \
    '{model:$model,messages:[{role:"user",content:$prompt}],max_tokens:$max_tokens}')

echo "Using model: ${MODEL_NAME}"
echo "Targeting endpoint: ${COMPLETION_URL}"
echo "Requests per tier: ${REQUESTS_PER_TIER}"
echo "----------------------------------------"

run_load_test() {
    local tier_name="$1"
    local api_key="$2"
    local successes=0
    local rate_limited=0
    local other=0
    local code

    echo "Starting test for: ${tier_name} tier"
    for ((i = 1; i <= REQUESTS_PER_TIER; i++)); do
        code=$(curl "${CURL_OPTIONS[@]}" -o /dev/null -w '%{http_code}' \
            -H "Authorization: Bearer ${api_key}" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" \
            "$COMPLETION_URL") || code=000

        case "$code" in
            200) successes=$((successes + 1)) ;;
            429) rate_limited=$((rate_limited + 1)) ;;
            *) other=$((other + 1)) ;;
        esac
    done

    echo "Results for ${tier_name}:"
    echo "  Successes (200): $successes"
    echo "  Rate limited (429): $rate_limited"
    echo "  Other responses: $other"
    echo "----------------------------------------"
}

run_load_test "Free" "$MAAS_FREE_API_KEY"
run_load_test "Premium" "$MAAS_PREMIUM_API_KEY"
