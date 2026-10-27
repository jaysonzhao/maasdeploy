#!/usr/bin/env python3
"""Exercise real structured decisions; never write credentials to results."""
import argparse
import base64
import datetime
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request


def oc(*args):
    return subprocess.check_output(['oc', *args], text=True).strip()


def request(url, payload=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if '/jev-maas/jev-latest/' in url:
        headers['X-MaaS-Subscription'] = 'jev-decisions'
    req = urllib.request.Request(url, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            return response.status, json.load(response), time.monotonic() - started
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error)
        except (ValueError, UnicodeError):
            body = {'error': 'non-JSON error response'}
        return error.code, body, time.monotonic() - started


QUESTIONS = {
    'urgent': {'type': 'noul', 'instructions': 'Does this incident need a response within one hour?'},
    'category': {'type': 'choice', 'instructions': 'Choose the incident category.',
                 'criteria': {'billing': 'Payment issue', 'outage': 'Service unavailable', 'other': 'Anything else'}},
    'severity': {'type': 'score', 'instructions': 'Rate the severity.',
                 'criteria': ['low', 'medium', 'high']},
}


def validate(body):
    urgent = body['answers']['urgent']
    assert urgent['type'] == 'noul' and 0 <= urgent['noul'] <= 1, body
    category = body['answers']['category']
    assert category['choice'] in QUESTIONS['category']['criteria'], body
    assert abs(sum(category['probabilities'].values()) - 1) < 0.02, body
    assert body['answers']['severity']['type'] == 'score', body
    assert body['diagnostics']['steps'] == 1, body
    assert body['diagnostics']['timing']['reads'] >= 1, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--direct-only', action='store_true')
    parser.add_argument('--output', default='evidence/test-results.json')
    args = parser.parse_args()
    key = base64.b64decode(oc('get', 'secret', 'jev-backend-key', '-n', 'jev-maas',
                             '-o', 'jsonpath={.data.API_KEY}')).decode()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    forward = subprocess.Popen(['oc', 'port-forward', '-n', 'jev-maas', 'service/jev-decision',
                                f'{port}:8011', '--address=127.0.0.1'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'cluster': oc('whoami', '--show-server'), 'cases': []}
    try:
        local = f'http://127.0.0.1:{port}'
        for _ in range(60):
            if forward.poll() is not None:
                raise RuntimeError('port-forward exited')
            try:
                if request(local + '/health')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('decision service did not become healthy')
        status, _, _ = request(local + '/v1/systemone', {})
        assert status == 401, status
        results['direct_missing_key_status'] = status
        states = {
            'urgent': 'Production checkout is unavailable and all customers cannot pay.',
            'routine': 'Please update the documentation link during the next planned maintenance.',
            'ambiguous': 'A few customers report intermittent delays; impact is unconfirmed.',
        }
        for name, ticket in states.items():
            payload = {'model': 'jev-latest', 'state': {'ticket': ticket}, 'questions': QUESTIONS,
                       'samples': 1, 'steps': 1}
            status, body, seconds = request(local + '/v1/systemone', payload, key)
            assert status == 200, (status, body)
            validate(body)
            results['cases'].append({'path': 'direct/systemone', 'case': name,
                                     'status': status, 'seconds': round(seconds, 3), 'response': body})
        status, _, _ = request(local + '/v1/systemone', {'questions': {}}, key)
        assert status in (400, 422), status
        results['malformed_status'] = status
        if not args.direct_only:
            route = oc('get', 'route', 'jev-decision', '-n', 'jev-maas', '-o', 'jsonpath={.spec.host}')
            native_url = 'https://' + route + '/v1/systemone'
            native_payload = {'model': 'jev-latest', 'state': {'ticket': states['urgent']},
                              'questions': QUESTIONS, 'samples': 1, 'steps': 1}
            status, _, _ = request(native_url, native_payload)
            assert status == 401, status
            results['https_missing_key_status'] = status
            status, body, seconds = request(native_url, native_payload, key)
            assert status == 200, (status, body)
            validate(body)
            results['cases'].append({'path': 'https/systemone', 'case': 'urgent',
                                     'status': status, 'seconds': round(seconds, 3), 'response': body})
            base = oc('get', 'maasmodelref', 'jev-latest', '-n', 'jev-maas',
                      '-o', 'jsonpath={.status.endpoint}').rstrip('/')
            url = base + '/jev-maas/jev-latest/v1/chat/completions'
            # The adapter accepts a JSON question schema in the system message.
            schema = {'questions': [
                {'id': 'urgent', **QUESTIONS['urgent']},
                {'id': 'category', 'type': 'choice', 'instructions': QUESTIONS['category']['instructions'],
                 'options': [{'name': k, 'description': v} for k, v in QUESTIONS['category']['criteria'].items()]},
                {'id': 'severity', 'type': 'score', 'instructions': QUESTIONS['severity']['instructions'],
                 'levels': QUESTIONS['severity']['criteria']},
            ], 'samples': 1, 'steps': 1}
            payload = {'model': 'jev-latest', 'messages': [
                {'role': 'system', 'content': json.dumps(schema)},
                {'role': 'user', 'content': json.dumps({'ticket': states['urgent']})}]}
            status, _, _ = request(url, payload)
            assert status in (401, 403), status
            results['maas_missing_key_status'] = status
            token = oc('create', 'token', 'jev-client', '-n', 'jev-maas', '--duration=10m')
            status, models, _ = request(base + '/v1/models', token=token)
            assert status == 200, (status, models)
            assert any(model['id'] == 'jev-latest' for model in models['data']), models
            results['maas_model_discovery_status'] = status
            status, body, seconds = request(url, payload, token)
            assert status == 200, (status, body)
            decision = json.loads(body['choices'][0]['message']['content'])
            validate(decision)
            assert body['usage']['prompt_tokens'] > 0, body['usage']
            results['cases'].append({'path': 'maas/chat/completions', 'case': 'urgent',
                                     'status': status, 'seconds': round(seconds, 3), 'response': body})
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps({'passed': len(results['cases']), 'results': str(output)}))
    finally:
        forward.terminate()
        forward.wait(timeout=10)


if __name__ == '__main__':
    main()
