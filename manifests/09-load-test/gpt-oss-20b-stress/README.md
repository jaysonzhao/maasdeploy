# Continuous GPT-OSS-20B stress load

This Deployment maintains 256 concurrent streaming chat requests through the MaaS API to `gpt-oss-20b` in project `llm`. Each request uses 64 varied synthetic records and requests 1,024 output tokens with `ignore_eos=true` to sustain generation. It starts the next request immediately after a successful response and runs until stopped.

The dedicated `gpt-oss-20b-stress` MaaS subscription allows 10,000,000 tokens per minute for only `system:serviceaccount:maas-load-test:gpt-oss-20b-stress`. The matching auth policy names that same identity. Kubernetes projects and rotates its one-hour token; the client rereads the token on every request. No API key, long-lived token, or additional Kubernetes RBAC binding is needed. The client validates HTTPS certificates.

## Start and stop

Run from the repository root with `oc` logged into the intended cluster:

```bash
./scripts/run-gpt-oss-stress.sh start
./scripts/run-gpt-oss-stress.sh status
./scripts/run-gpt-oss-stress.sh stop
```

The model must already be Ready and MaaS must be configured. Update `MAAS_BASE_URL` in `kustomization.yaml` for another cluster. The helper creates `maas-load-test` only if absent. This bundle keeps the shared namespace outside its resource list so deleting this bundle does not delete other load tests.

The equivalent immediate pause is:

```bash
oc scale deployment/gpt-oss-20b-stress -n maas-load-test --replicas=0
```

## Tune demand

Increase or decrease concurrency and output length with environment overrides. Each change restarts the load pod:

```bash
oc set env deployment/gpt-oss-20b-stress -n maas-load-test CONCURRENCY=256 MAX_TOKENS=2048
oc set env deployment/gpt-oss-20b-stress -n maas-load-test CONCURRENCY=64 MAX_TOKENS=1024
```

The client supports 1–512 concurrent workers. It starts workers 0.2 seconds apart to reduce an initial authorization burst; `STARTUP_INTERVAL_SECONDS` controls that ramp. `PROMPT_RECORDS` controls varied input length, and `REQUEST_TIMEOUT_SECONDS` defaults to 600 seconds so queued requests can finish. Edit the generator settings in `kustomization.yaml` to save a new default. Heavy traffic can increase latency for other callers of this model.

## Observe

```bash
oc logs -f deployment/gpt-oss-20b-stress -n maas-load-test
oc exec deployment/gpt-oss-20b-kserve -n llm -c main -- \
  nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw --format=csv
```

Every 30 seconds the client prints JSON counters, active requests, completed-request throughput, completed output-token throughput, HTTP errors, and streaming TTFT/latency percentiles. The first throughput report can be zero while the initial batch is still generating. Reported token throughput is based on usage from completed requests. Prompts, generated text, and authentication tokens are not logged. HTTP failures back off rather than spin; 401/403 failures wait 30 seconds. Use GPU utilization and the serving engine's running/waiting requests to distinguish saturated inference from rate limiting or client errors.

To remove only this stress test, stop it first, then delete its bundle:

```bash
./scripts/run-gpt-oss-stress.sh stop
oc delete -k manifests/09-load-test/gpt-oss-20b-stress/
oc delete configmap -n maas-load-test -l app.kubernetes.io/name=gpt-oss-20b-stress
```

## Observed saturation

On 2026-10-26, this configuration on the sandbox L40S reached 166–177 running requests with 78–90 waiting and 99.5–99.7% use of the vLLM KV-cache pool. Engine generation throughput was approximately 3,200–3,700 tokens/second in the sampled ten-second windows. The first client report after the ramp recorded 154 completed requests, zero errors, and 256 requests in flight. These are observations for this model, runtime, and workload; KV-cache percentage describes the engine's allocated cache pool, rather than all physical GPU memory.
