#!/usr/bin/env bash
set -euo pipefail

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

if ! oc get namespace maas-load-test >/dev/null 2>&1; then
    echo "Namespace maas-load-test does not exist; nothing to clean up."
    exit 0
fi

CLUSTER_DOMAIN="$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')"
MAAS_BASE_URL="${MAAS_BASE_URL:-https://maas.${CLUSTER_DOMAIN}}"
ADMIN_TOKEN="$(oc whoami -t)"
VERIFY_TLS="${MAAS_VERIFY_TLS:-true}"
CURL_OPTIONS=(-sS)
case "$VERIFY_TLS" in
    false|False|FALSE|0|no|No|NO) CURL_OPTIONS+=(-k) ;;
esac

for tier in FREE PREMIUM; do
    if [[ "$tier" == "FREE" ]]; then
        tier_label="free"
    else
        tier_label="premium"
    fi
    encoded_id="$(oc get secret maas-loadtest-keys -n maas-load-test \
        -o "jsonpath={.data.${tier}_API_KEY_ID}" 2>/dev/null || true)"
    api_key_id="$(printf '%s' "$encoded_id" | jq -Rr 'if length == 0 then "" else @base64d end')"
    if [[ -n "$api_key_id" ]]; then
        status="$(curl "${CURL_OPTIONS[@]}" -o /dev/null -w '%{http_code}' \
            -X DELETE "${MAAS_BASE_URL}/maas-api/v1/api-keys/${api_key_id}" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" || echo 000)"
        case "$status" in
            2??|404) echo "${tier_label} API key revoked or already expired." ;;
            *) echo "Could not revoke ${tier_label} API key (HTTP ${status}); it will expire within one hour." >&2 ;;
        esac
    fi
done

oc delete namespace maas-load-test --wait=false
echo "Namespace deletion started; its Job, Secret, ConfigMaps, and logs are being removed."
