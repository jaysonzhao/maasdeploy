#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-persistent}" in
  persistent) bundle=. ;;
  ephemeral) bundle=overlays/ephemeral ;;
  *) echo 'Usage: ./deploy.sh [persistent|ephemeral]' >&2; exit 1 ;;
esac
oc whoami >/dev/null
echo "Target: $(oc whoami --show-server)"
python3 - <<'CHECK'
import hashlib,pathlib
p=pathlib.Path('base/vendor/structured_server.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='7cd9aa0081090c064eaac28db0f54f812749eeb3ae787d7f7653d2e35d8a938f'
CHECK
oc apply -f base/namespace.yaml
oc create configmap jev-structured -n jev-maas --from-file=structured_server.py=base/maas_server.py --from-file=vendor_structured_server.py=base/vendor/structured_server.py --dry-run=client -o yaml | oc apply -f -
if ! oc get secret jev-backend-key -n jev-maas >/dev/null 2>&1; then
    python3 - <<'KEY' | oc apply -f -
import base64,json,secrets
key=base64.b64encode(secrets.token_urlsafe(32).encode()).decode()
print(json.dumps({'apiVersion':'v1','kind':'Secret','metadata':{'name':'jev-backend-key','namespace':'jev-maas','labels':{'inference.llm-d.ai/ipp-managed':'true'}},'type':'Opaque','data':{'API_KEY':key,'api-key':key}}))
KEY
fi
oc label secret jev-backend-key -n jev-maas inference.llm-d.ai/ipp-managed=true --overwrite
oc apply -f image-check.yaml
oc wait --for=condition=complete job/jev-image-check -n jev-maas --timeout=600s
oc logs job/jev-image-check -n jev-maas
oc apply -k "$bundle"
echo 'Model initialization started. Follow logs and wait for rollout readiness before publishing:'
echo 'oc logs deployment/jev-diffusiongemma -n jev-maas -c vllm -f'
echo 'oc rollout status deployment/jev-diffusiongemma -n jev-maas --timeout=60s'
echo 'Run python3 test.py --direct-only, then oc apply -f route.yaml,maas.yaml, then python3 test.py.'
