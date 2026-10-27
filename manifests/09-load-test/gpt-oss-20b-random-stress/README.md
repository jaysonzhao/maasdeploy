# Randomized continuous GPT-OSS-20B stress

This additional client targets the same `llm/gpt-oss-20b` model as
`gpt-oss-20b-stress`. It runs independently and does not change the existing
stress deployment or serving configuration.

Every request begins with 192 randomly selected words, followed by a UUID, one
of eight engineering tasks, and 32–96 shuffled synthetic records. There is no
fixed system message. This reduces reusable prompt prefixes; it does not
guarantee equal routing across serving replicas. The currently inspected GPT
route uses a Kubernetes Service with session affinity disabled, rather than
an llm-d scheduling endpoint.

## Start, observe, stop

From the repository root:

```sh
./scripts/run-gpt-oss-random-stress.sh start
./scripts/run-gpt-oss-random-stress.sh status
./scripts/run-gpt-oss-random-stress.sh stop
```

Defaults: one client replica, 256 concurrent streaming requests, 1,024 output
tokens per request, `ignore_eos=true`, and a 600-second socket timeout. Load
continues until scaled to zero. Shared model latency can increase.

Tune `CONCURRENCY`, `MAX_TOKENS`, `PROMPT_PREFIX_WORDS`, and `PROMPT_RECORDS`
in `kustomization.yaml`, then run the start command again. Each client replica
adds another full concurrency budget. The generated ConfigMap hash triggers
a rollout when settings or the runner change.

The dedicated service account uses a rotating projected token and a dedicated
MaaS authorization policy/subscription limited to this model. Its subscription
allows 10,000,000 tokens per minute. No credential is stored in this bundle.

The client prints aggregate completions, token throughput, TTFT, latency and
HTTP errors every 30 seconds after the initial worker ramp. Prompt and response
content are discarded. HTTP 429 indicates governance throttling; 401/403
indicates authentication or authorization trouble.

Requests carry `User-Agent: maas-gpt-oss-random-stress/1.0` and a unique request
ID, and close each client connection. Filter gateway access logs by that user
agent to attribute completed requests to upstream pod addresses. Compare those
addresses with the Service's EndpointSlices; background stress traffic is not
evidence of this client's distribution.

```sh
oc logs deployment/maas-default-gateway-openshift-default -n openshift-ingress \
  --since=10m | rg 'maas-gpt-oss-random-stress/1.0'
oc get endpointslice -n llm \
  -l kubernetes.io/service-name=gpt-oss-20b-kserve-workload-svc -o yaml
```

Remove only this additional workload and its governance resources:

```sh
oc delete -k manifests/09-load-test/gpt-oss-20b-random-stress/
```

Do not delete the shared `maas-load-test` namespace to clean up this client.
