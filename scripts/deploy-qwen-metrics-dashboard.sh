#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${REPO_ROOT}/manifests/12-qwen-metrics-dashboard"
APP_DIR="${REPO_ROOT}/apps/qwen-metrics"
NAMESPACE="qwen-metrics-dashboard"

for dependency in oc openssl; do
    if ! command -v "${dependency}" >/dev/null 2>&1; then
        echo "Required command not found: ${dependency}" >&2
        exit 1
    fi
done

if ! oc whoami >/dev/null 2>&1; then
    echo "Log in to the target OpenShift cluster before deploying the Qwen metrics app." >&2
    exit 1
fi

echo "Deploying the Qwen metrics app to $(oc whoami --show-server) as $(oc whoami)."
oc apply -f "${MANIFEST_DIR}/namespace.yaml" >/dev/null

oc create configmap qwen-metrics-dashboard-source -n "${NAMESPACE}" \
    --from-file="${APP_DIR}/index.html" \
    --from-file="${APP_DIR}/styles.css" \
    --from-file="${APP_DIR}/app.js" \
    --from-file="${APP_DIR}/server.py" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null

if ! oc get secret qwen-metrics-dashboard-cookie -n "${NAMESPACE}" >/dev/null 2>&1; then
    COOKIE_SECRET="$(openssl rand -base64 32 | tr -d '\n')"
    oc create secret generic qwen-metrics-dashboard-cookie -n "${NAMESPACE}" \
        --from-literal="session_secret=${COOKIE_SECRET}" \
        --dry-run=client -o yaml | oc apply -f - >/dev/null
    unset COOKIE_SECRET
fi

oc apply -k "${MANIFEST_DIR}" >/dev/null
oc rollout restart deployment/qwen-metrics-dashboard -n "${NAMESPACE}" >/dev/null
oc rollout status deployment/qwen-metrics-dashboard -n "${NAMESPACE}" --timeout=180s
APP_HOST="$(oc get route qwen-metrics-dashboard -n "${NAMESPACE}" -o jsonpath='{.spec.host}')"
echo "Qwen metrics app is ready: https://${APP_HOST}"
