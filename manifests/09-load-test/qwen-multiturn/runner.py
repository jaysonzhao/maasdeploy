"""Authenticate the existing benchmark and retry safe model discovery requests."""
import asyncio
import json
import os
import runpy

import httpx


api_key = os.environ['MAAS_API_KEY']
original_init = httpx.AsyncClient.__init__
original_request = httpx.AsyncClient.request


def authenticated_init(self, *args, **kwargs):
    headers = dict(kwargs.pop('headers', {}) or {})
    headers['Authorization'] = 'Bearer ' + api_key
    kwargs['headers'] = headers
    # The benchmark image defaults to verify=False. The MaaS ingress certificate
    # is trusted by this image; retain certificate verification for all calls.
    kwargs['verify'] = True
    return original_init(self, *args, **kwargs)


async def resilient_request(self, method, url, *args, **kwargs):
    discovery = method.upper() == 'GET' and str(url).split('?', 1)[0].rstrip('/').endswith('/models')
    if not discovery:
        return await original_request(self, method, url, *args, **kwargs)
    kwargs['timeout'] = 10.0
    for attempt in range(5):
        try:
            response = await original_request(self, method, url, *args, **kwargs)
            if response.status_code not in (500, 502, 503, 504) or attempt == 4:
                return response
            failure = 'http_' + str(response.status_code)
            await response.aclose()
        except httpx.TransportError as error:
            if attempt == 4:
                raise
            failure = type(error).__name__
        delay = 2 ** attempt
        print(json.dumps({'event': 'model_discovery_retry', 'attempt': attempt + 1,
                          'error': failure, 'delay_seconds': delay}), flush=True)
        await asyncio.sleep(delay)


httpx.AsyncClient.__init__ = authenticated_init
httpx.AsyncClient.request = resilient_request
runpy.run_path('/opt/app-root/src/multi-turn-benchmark.py', run_name='__main__')
