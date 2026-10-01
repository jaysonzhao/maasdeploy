#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${REPO_ROOT}/manifests/11-maas-portal"
NAMESPACE="maas-portal"

for dependency in oc openssl; do
    if ! command -v "${dependency}" >/dev/null 2>&1; then
        echo "Required command not found: ${dependency}" >&2
        exit 1
    fi
done

if ! oc whoami >/dev/null 2>&1; then
    echo "Log in to the target OpenShift cluster before deploying the portal." >&2
    exit 1
fi

CLUSTER_SERVER="$(oc whoami --show-server)"
CLUSTER_USER="$(oc whoami)"
CLUSTER_DOMAIN="$(oc get ingress.config/cluster -o jsonpath='{.spec.domain}')"
if [[ -z "${CLUSTER_DOMAIN}" ]]; then
    echo "Could not discover the OpenShift ingress domain." >&2
    exit 1
fi

DASHBOARD_HOST="$(oc get routes -n redhat-ods-applications \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.host}{"\n"}{end}' 2>/dev/null \
    | awk '$1 ~ /dashboard/ && $2 != "" { print $2; exit }' || true)"
if [[ -z "${DASHBOARD_HOST}" ]]; then
    echo "Could not find the OpenShift AI dashboard Route in redhat-ods-applications." >&2
    echo "Install the RHOAI dashboard first, then rerun this script." >&2
    exit 1
fi

CONSOLE_URL="https://console-openshift-console.apps.${CLUSTER_DOMAIN}"
DASHBOARD_URL="https://${DASHBOARD_HOST}"
CLUSTER_NAME="${CLUSTER_DOMAIN}"

echo "Deploying the MaaS guided journey to ${CLUSTER_SERVER} as ${CLUSTER_USER}."
oc apply -f "${MANIFEST_DIR}/namespace.yaml" >/dev/null

oc create configmap maas-guided-journey-source -n "${NAMESPACE}" \
    --from-file="${REPO_ROOT}/portal/index.html" \
    --from-file="${REPO_ROOT}/portal/styles.css" \
    --from-file="${REPO_ROOT}/portal/app.js" \
    --from-file="${REPO_ROOT}/portal/server.py" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null

oc create configmap maas-guided-journey-settings -n "${NAMESPACE}" \
    --from-literal="DASHBOARD_URL=${DASHBOARD_URL}" \
    --from-literal="CONSOLE_URL=${CONSOLE_URL}" \
    --from-literal="CLUSTER_NAME=${CLUSTER_NAME}" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null

if ! oc get secret maas-guided-journey-cookie -n "${NAMESPACE}" >/dev/null 2>&1; then
    COOKIE_SECRET="$(openssl rand -base64 32 | tr -d '\n')"
    oc create secret generic maas-guided-journey-cookie -n "${NAMESPACE}" \
        --from-literal="session_secret=${COOKIE_SECRET}" \
        --dry-run=client -o yaml | oc apply -f - >/dev/null
    unset COOKIE_SECRET
fi

oc apply -k "${MANIFEST_DIR}" >/dev/null
oc rollout restart deployment/maas-guided-journey -n "${NAMESPACE}" >/dev/null
oc rollout status deployment/maas-guided-journey -n "${NAMESPACE}" --timeout=180s
PORTAL_HOST="$(oc get route maas-guided-journey -n "${NAMESPACE}" -o jsonpath='{.spec.host}')"
echo "Portal is ready: https://${PORTAL_HOST}"
echo "Dashboard link: ${DASHBOARD_URL}"
