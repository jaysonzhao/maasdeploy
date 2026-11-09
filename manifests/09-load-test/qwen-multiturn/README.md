# Qwen multi-turn load CronJobs

This bundle maintains the two existing MaaS workloads in `maas-load-test`:

- `qwen-llmd-multiturn` targets `llm/redhataiqwen25-7b-instruct`.
- `qwen-vllm-multiturn` targets `llm/redhataiqwen25-7b-instruct-vll`.

Each runs every two minutes with 10 conversations, 10 turns per conversation,
8 parallel workers, 96 maximum output tokens per response, and 0.1–0.5 seconds
between turns. The request timeout remains 60 seconds. Jobs have a 240-second
deadline and `concurrencyPolicy: Forbid`; a busy job can cause a scheduled tick
to be skipped. The bundle preserves the existing load parameters.

The benchmark image is pinned to its inspected running digest:
`quay.io/hayesphilip/multi-turn-benchmark@sha256:239c2a41220698b355b63c9c7c58da87069daaac48114b00a9c854df962a58fa`.
Seed documents and the upstream benchmark script are already in that image.

## Apply and observe

The namespace, Qwen models, MaaS access policies and existing Secret
`maas-multiturn-auth-20261002` must exist. Its `api-key` entry must contain a
valid key authorized for both models. This bundle references that Secret;
it neither exports its value nor rotates it.

```sh
oc apply -k manifests/09-load-test/qwen-multiturn/
oc get cronjob,job,pod -n maas-load-test
oc logs -n maas-load-test job/<job-name>
```

The ConfigMap name includes a content hash. New jobs pick up wrapper changes;
already running jobs keep their original configuration. The wrapper injects
the existing key into HTTPX clients, enables TLS certificate verification,
and retries only safe discovery GETs ending in `/models`.

Discovery allows five attempts with a ten-second timeout per attempt and
1, 2, 4, and 8 second delays. Transport errors and HTTP 500/502/503/504 are
retryable. HTTP 401/403 are not retried. Exhausted failures remain visible
as failed Jobs. Inference POSTs are not retried by the wrapper, avoiding
duplicate model generations and misleading throughput counts.

## Recovery performed on 2026-11-09

Both benchmark clients failed at initial `/models` discovery with
`httpx.RemoteProtocolError: Server disconnected without sending a response`.
Both model services and MaaS references were Ready. GPT clients also failed,
and authenticated and unauthenticated requests timed out through both the
public route and the internal gateway Service.

The gateway had two WASM artifact fetch failures and no active Kuadrant WASM
runtime. The policy artifact server was available again, serving 5,427,348
bytes with SHA256
`8ebb4eb0910cf689981e50c7ff78df3070398ede17c3276d9048bdce3d30f806`,
matching the managed EnvoyFilter's expected checksum. Restarting only the
MaaS gateway loaded the policy module successfully. Both Qwen discovery
endpoints then returned HTTP 200 in approximately 0.1 seconds, while
unauthenticated discovery returned HTTP 401.

For a recurrence, inspect gateway policy-module counters, verify the artifact
service is healthy and the checksum matches the current managed configuration,
then recover the gateway runtime. Do not assume the artifact digest above is
correct after an operator upgrade.

```sh
oc logs deployment/maas-default-gateway-openshift-default -n openshift-ingress
oc get service,endpointslice -n openshift-operators | rg kuadrant-operator-wasm
# After confirming the required artifact is available with its expected checksum:
oc rollout restart deployment/maas-default-gateway-openshift-default -n openshift-ingress
oc rollout status deployment/maas-default-gateway-openshift-default -n openshift-ingress
```

Authentication and rate-limit settings were retained. No Qwen model, GPU
allocation, serving runtime, or benchmark load setting changed during this
repair. See `evidence.json` for observed job outcomes.
