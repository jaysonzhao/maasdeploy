#!/usr/bin/env python3
"""Add MaaS and CPU TinyLlama to an existing OpenShift AI 3.5 installation.

Requires oc, Python 3, PyYAML, and an authenticated cluster-admin context.
Preserves existing operator subscriptions, DSC components, and dashboard flags.
"""
import argparse
import base64
import json
from pathlib import Path
import secrets
import subprocess
import time
import yaml

ROOT = Path(__file__).resolve().parents[1]
INFRA = 'redhat-ai-gateway-infra'
MODEL = 'tinyllama-1-1b-chat-v1-0'


def oc(*args, data=None, optional=False):
    p = subprocess.run(['oc', '--request-timeout=30s', *args],
                       input=json.dumps(data) if data is not None else None,
                       text=True, capture_output=True)
    if p.returncode and not optional:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip() if not p.returncode else ''


def get(kind, name, ns=None):
    result = oc('get', kind, name, *(['-n', ns] if ns else []), '-o', 'json', optional=True)
    return json.loads(result) if result else None


def apply(obj):
    print(oc('apply', '-f', '-', data=obj), flush=True)


def patch(kind, name, spec, ns=None):
    print(oc('patch', kind, name, *(['-n', ns] if ns else []),
             '--type=merge', '-p', json.dumps(spec)), flush=True)


def manifest(path, namespace=None):
    for obj in yaml.safe_load_all((ROOT / path).read_text()):
        if obj:
            if namespace:
                obj['metadata']['namespace'] = namespace
            apply(obj)


def wait(description, predicate, seconds=600):
    deadline = time.monotonic() + seconds
    print('Waiting for ' + description, flush=True)
    while time.monotonic() < deadline:
        if predicate():
            print(description + ': ready', flush=True)
            return
        time.sleep(10)
    raise RuntimeError('Timed out waiting for ' + description)


def ready(kind, name, ns=None):
    obj = get(kind, name, ns) or {}
    return any(c['type'] == 'Ready' and c['status'] == 'True'
               for c in obj.get('status', {}).get('conditions', []))


def namespace(name, labels=None):
    apply({'apiVersion': 'v1', 'kind': 'Namespace',
           'metadata': {'name': name, 'labels': labels or {}}})


def platform():
    # Do not reapply the old umbrella subscriptions or replace the existing DSC.
    dsc = get('datasciencecluster', 'default-dsc')
    if not dsc or 'aigateway' not in dsc['spec']['components']:
        raise RuntimeError('This workflow requires an existing OpenShift AI 3.5 DSC with aigateway support')
    if dsc['spec']['components'].get('kserve', {}).get('managementState') != 'Managed':
        raise RuntimeError('Enable KServe before running this on-cluster model workflow')
    subscriptions = json.loads(oc('get', 'subscriptions', '-n', 'openshift-operators', '-o', 'json'))['items']
    matches = [s for s in subscriptions if s.get('spec', {}).get('name') == 'rhcl-operator']
    if len(matches) > 1:
        raise RuntimeError('Multiple RHCL subscriptions exist; resolve the duplicate before continuing')
    sub = matches[0] if matches else None
    subscription_name = sub['metadata']['name'] if sub else 'rhcl-operator'
    if not sub:
        obj = yaml.safe_load((ROOT / 'manifests/01-prerequisites/operators/connectivity-link/subscription.yaml').read_text())
        obj['spec'].update(channel='stable-1.4', startingCSV='rhcl-operator.v1.4.4')
        apply(obj)

    def operator_ready():
        s = get('subscription', subscription_name, 'openshift-operators') or {}
        plan_name = s.get('status', {}).get('installplan', {}).get('name')
        if plan_name:
            plan = get('installplan', plan_name, 'openshift-operators') or {}
            if not plan.get('spec', {}).get('approved'):
                names = plan.get('spec', {}).get('clusterServiceVersionNames', [])
                allowed = ('rhcl-operator.v1.4.', 'authorino-operator.v1.4.', 'limitador-operator.v1.4.', 'dns-operator.v1.4.')
                if not names or any(not n.startswith(allowed) for n in names):
                    raise RuntimeError('InstallPlan contains unrelated operator changes; inspect it before approval')
                patch('installplan', plan_name, {'spec': {'approved': True}}, 'openshift-operators')
        csv = s.get('status', {}).get('installedCSV') or s.get('status', {}).get('currentCSV')
        if csv and not csv.startswith('rhcl-operator.v1.4.'):
            raise RuntimeError('This OpenShift AI 3.5 workflow requires RHCL 1.4.x; existing subscription was preserved')
        return bool(csv and (get('csv', csv, 'openshift-operators') or {}).get('status', {}).get('phase') == 'Succeeded')

    wait('Connectivity Link operator', operator_ready)
    for name in ['namespace', 'service-annotation', 'kuadrant']:
        manifest(f'manifests/02-platform-config/kuadrant/{name}.yaml')
    wait('Kuadrant', lambda: ready('kuadrant', 'kuadrant', 'kuadrant-system'))
    patch('authorino', 'authorino', {'spec': {'listener': {'tls': {
        'enabled': True, 'certSecretRef': {'name': 'authorino-server-cert'}}}}}, 'kuadrant-system')
    print(oc('-n', 'kuadrant-system', 'set', 'env', 'deployment/authorino',
             'SSL_CERT_FILE=/etc/ssl/certs/openshift-service-ca/service-ca-bundle.crt',
             'REQUESTS_CA_BUNDLE=/etc/ssl/certs/openshift-service-ca/service-ca-bundle.crt'), flush=True)

    domain = get('ingress.config.openshift.io', 'cluster')['spec']['domain']
    ingress = get('ingresscontroller', 'default', 'openshift-ingress-operator')
    cert = ingress['spec'].get('defaultCertificate', {}).get('name', 'router-certs-default')
    for name in ['gatewayclass.yaml', 'gateway-resources.yaml']:
        manifest('manifests/02-platform-config/' + name)
    for path in ['manifests/02-platform-config/gateway.yaml.tmpl',
                 'manifests/03-maas-platform/openshift-gateway-setup/route.yaml.tmpl']:
        text = (ROOT / path).read_text().replace('${CLUSTER_DOMAIN}', domain).replace('${CERT_NAME}', cert)
        apply(yaml.safe_load(text))

    # Merge the monitoring YAML data rather than replacing an existing config.
    monitoring = get('configmap', 'cluster-monitoring-config', 'openshift-monitoring')
    config = yaml.safe_load((monitoring or {}).get('data', {}).get('config.yaml', '')) or {}
    if config.get('enableUserWorkload') is not True:
        config['enableUserWorkload'] = True
        obj = {'apiVersion': 'v1', 'kind': 'ConfigMap',
               'metadata': {'name': 'cluster-monitoring-config', 'namespace': 'openshift-monitoring'},
               'data': {'config.yaml': yaml.safe_dump(config)}}
        if monitoring:
            patch('configmap', 'cluster-monitoring-config', {'data': obj['data']}, 'openshift-monitoring')
        else:
            apply(obj)
    namespace(INFRA, {'maas.opendatahub.io/gateway-access': 'true'})
    existing = get('secret', 'postgres-creds', INFRA)
    if existing:
        password = base64.b64decode(existing['data']['POSTGRES_PASSWORD']).decode()
    else:
        password = secrets.token_urlsafe(32)
        apply({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'postgres-creds', 'namespace': INFRA},
               'type': 'Opaque', 'stringData': {'POSTGRES_USER': 'maas', 'POSTGRES_DB': 'maas', 'POSTGRES_PASSWORD': password}})
    if not get('secret', 'maas-db-config', INFRA):
        apply({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'maas-db-config', 'namespace': INFRA},
               'type': 'Opaque', 'stringData': {'DB_CONNECTION_URL':
                   f'postgresql://maas:{password}@postgres.{INFRA}.svc:5432/maas?sslmode=disable'}})
    for name in ['postgres-pvc', 'postgres-service', 'postgres-deployment']:
        manifest(f'manifests/03-maas-platform/{name}.yaml', INFRA)
    wait('PostgreSQL', lambda: (get('deployment', 'postgres', INFRA) or {}).get('status', {}).get('readyReplicas', 0) >= 1)
    patch('datasciencecluster', 'default-dsc', {'spec': {'components': {'aigateway': {
        'managementState': 'Managed', 'modelsAsAService': {'managementState': 'Managed'}}}}})
    patch('odhdashboardconfig', 'odh-dashboard-config', {'spec': {'dashboardConfig': {
        'modelAsService': True, 'vLLMDeploymentOnMaaS': True, 'genAiStudio': True}}}, 'redhat-ods-applications')
    wait('MaaS API', lambda: (get('deployment', 'maas-api', INFRA) or {}).get('status', {}).get('readyReplicas', 0) >= 1)
    wait('default MaaS tenant', lambda: ready('maastenantconfig', 'default-tenant', 'models-as-a-service'))
    print('MaaS URL: https://maas.' + domain, flush=True)


def model():
    namespace('llm', {'opendatahub.io/generated-namespace': 'true', 'opendatahub.io/dashboard': 'true',
                      'maas.opendatahub.io/gateway-access': 'true'})
    print(oc('apply', '-k', str(ROOT / 'manifests/05-maas-models/tinyllama-cpu')), flush=True)
    wait('CPU TinyLlama', lambda: ready('llminferenceservice', MODEL, 'llm'), seconds=1200)
    wait('TinyLlama MaaS model reference', lambda: ready('maasmodelref', MODEL, 'llm'))
    wait('TinyLlama access policy', lambda: (get('maasauthpolicy', MODEL + '-access', 'models-as-a-service') or {}).get('status', {}).get('phase') == 'Active')
    for tier in ['free', 'premium']:
        wait('TinyLlama ' + tier + ' subscription', lambda tier=tier: (get('maassubscription', MODEL + '-' + tier, 'models-as-a-service') or {}).get('status', {}).get('phase') == 'Active')
    print('Model ID: publishers/llm/models/tinyllama-1.1b-chat-v1.0', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-server', required=True, help='Exact authorized OpenShift API URL')
    parser.add_argument('--platform-only', action='store_true')
    parser.add_argument('--model-only', action='store_true')
    args = parser.parse_args()
    if args.platform_only and args.model_only:
        parser.error('Choose at most one of --platform-only and --model-only')
    if oc('whoami', '--show-server').rstrip('/') != args.expected_server.rstrip('/'):
        parser.error('Current oc context is not the expected server')
    print('Cluster: ' + oc('whoami', '--show-server') + '; identity: ' + oc('whoami'), flush=True)
    if not args.model_only:
        platform()
    if not args.platform_only:
        model()
