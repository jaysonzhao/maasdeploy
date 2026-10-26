#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="$SCRIPT_DIR/../manifests/09-load-test/gpt-oss-20b-stress"
ACTION="${1:-start}"

case "$ACTION" in
    start|stop|status) ;;
    *) echo "Usage: $0 [start|stop|status]" >&2; exit 1 ;;
esac
oc whoami >/dev/null
echo "Cluster: $(oc whoami --show-server)"

case "$ACTION" in
    start)
        ready="$(oc get llminferenceservice gpt-oss-20b -n llm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')"
        if [ "$ready" != "True" ]; then
            echo "gpt-oss-20b is not Ready; restore the serving workload before starting stress." >&2
            exit 1
        fi
        if ! oc get namespace maas-load-test >/dev/null 2>&1; then
            oc create namespace maas-load-test
        fi
        oc apply -f "$MANIFEST_DIR/service-account.yaml"
        oc apply -f "$MANIFEST_DIR/governance.yaml"
        oc wait --for=condition=Ready maasauthpolicy/gpt-oss-20b-stress-access -n models-as-a-service --timeout=60s
        oc wait --for=condition=Ready maassubscription/gpt-oss-20b-stress -n models-as-a-service --timeout=60s
        oc apply -k "$MANIFEST_DIR"
        oc rollout status deployment/gpt-oss-20b-stress -n maas-load-test --timeout=120s
        echo "Continuous load is running. Stop: $0 stop"
        ;;
    stop)
        oc scale deployment/gpt-oss-20b-stress -n maas-load-test --replicas=0
        ;;
    status)
        oc get deployment,pods -n maas-load-test -l app.kubernetes.io/name=gpt-oss-20b-stress
        ready="$(oc get deployment gpt-oss-20b-stress -n maas-load-test -o jsonpath='{.status.readyReplicas}')"
        if [ "${ready:-0}" -gt 0 ]; then
            oc logs deployment/gpt-oss-20b-stress -n maas-load-test --tail=5
        fi
        ;;
esac
