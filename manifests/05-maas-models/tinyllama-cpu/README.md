# TinyLlama on CPU with MaaS

This bundle serves the real `TinyLlama/TinyLlama-1.1B-Chat-v1.0` model on x86_64 AVX2 CPU workers. No GPU device, GPU operator, time slicing, or privileged SCC is required.

- Modelcar: `quay.io/redhat-ai-services/modelcar-catalog:tinyllama-1.1b-chat-v1.0` (validated image digest `sha256:10025c5a4406973ecb4f80b71dd3e2f31a5cf837c25d21ffd482c423289e324b`).
- CPU runtime: `registry.redhat.io/rhaiis/vllm-cpu-rhel9:3.3.0`, pinned in `llm/runtime.yaml` to `sha256:f05e773647dddd37ec6c2215cb14bec87e4ab5a7d37f2e110d16cd92355427d3`; vLLM `0.13.0+rhai11`, PyTorch `2.9.1`.
- One serving replica: requests 4 CPU / 12 GiB, limits 6 CPU / 16 GiB. Four OpenMP threads, 1 GiB KV cache, float32 weights, 2,048-token context, at most eight simultaneous sequences. These are deployment settings, not measured throughput guarantees.
- Hardware profile: `redhat-ods-applications/tinyllama-cpu`. Its CPU and memory identifiers supply the default requests and maximum limits; its node scheduling supplies the worker selector through Kustomize replacements. The LLMInferenceService references this profile through both hardware-profile annotations. Edit `llm/hardwareprofile.yaml` and reapply the bundle to change these settings together; applying the HardwareProfile alone does not resize the workload.
- Kubernetes service/ref name: `tinyllama-1-1b-chat-v1-0`, namespace `llm`.
- Public MaaS model ID: `publishers/llm/models/tinyllama-1.1b-chat-v1.0`.
- Free subscription: `tinyllama-1-1b-chat-v1-0-free`, 100 tokens/minute, priority 10.
- Premium subscription: `tinyllama-1-1b-chat-v1-0-premium`, 100,000 tokens/minute, priority 20.

Both subscriptions and the access policy grant membership to `system:authenticated`, matching this repository's demo convention. Bind an API key to the desired subscription when creating it. Without an explicit subscription selection, the higher-priority premium subscription can be chosen. For a controlled rollout, change the policy subjects and subscription owners to your actual groups before applying.

## Install onto an existing OpenShift AI 3.5 cluster

Log in to the intended cluster as an administrator with KServe already Managed. Ensure the cluster can pull the Red Hat CPU runtime and public modelcar. Install Python 3 and PyYAML locally, then run from the repository root:

```bash
python3 scripts/setup-maas-cpu.py \
  --expected-server https://api.<your-cluster>:6443
```

The script checks the selected API server; installs Connectivity Link 1.4 only if a subscription for its package is absent; approves only a plan containing the RHCL/Authorino/Limitador/DNS operators; creates Kuadrant, service certificates, a separate MaaS gateway, and an ingress passthrough route; enables User Workload Monitoring while preserving existing monitoring settings; provisions PostgreSQL and real generated credentials in `redhat-ai-gateway-infra`; merge-patches only `aigateway.managementState` and `aigateway.modelsAsAService.managementState`; enables supported MaaS/Gen AI dashboard flags; and deploys the model and governance resources.

The script preserves other DSC components, the existing `data-science-gateway`, and existing dashboard fields. It does not apply the repository's older whole-DSC or operator umbrella manifests. Existing subscriptions are discovered by package name and retained.

PostgreSQL uses a 20 GiB RWO PVC and the repo's single-instance lab deployment. Its in-cluster database connection uses `sslmode=disable`; use managed PostgreSQL with TLS and backups for production. Passwords stay in Kubernetes Secrets and are never written into manifests or printed. CPU AVX2 serving in AI Inference Server 3.3 is Technology Preview.

Platform-only and model-only resumes are supported:

```bash
python3 scripts/setup-maas-cpu.py --expected-server https://api.<your-cluster>:6443 --platform-only
python3 scripts/setup-maas-cpu.py --expected-server https://api.<your-cluster>:6443 --model-only

# Alternative on an already configured MaaS cluster:
./scripts/deploy-model.sh --model tinyllama-cpu
./scripts/setup-maas.sh --from-phase 5 --model tinyllama-cpu --skip-verify
```

The base CPU config overrides the serving image; the installed KServe template retains modelcar mounting, health probes, and backend TLS. It contains no accelerator resource request. The node selector requires an amd64 worker; verify `avx2` in `/proc/cpuinfo` on the chosen worker before deployment on different hardware.

## Call the model

Discover the exact model ID through `GET /maas-api/v1/models`. Create an API key through the AI dashboard or `POST /maas-api/v1/api-keys` with an authenticated OpenShift bearer token and `subscription` set to one of the names above. Keep keys in protected environment variables or a secrets manager.

```bash
# Set MAAS_URL, MAAS_API_KEY, and INGRESS_CA outside shell history.
curl --cacert "$INGRESS_CA" "$MAAS_URL/v1/chat/completions" \
  -H "Authorization: Bearer $MAAS_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"publishers/llm/models/tinyllama-1.1b-chat-v1.0","messages":[{"role":"user","content":"Say hello in one short sentence."}],"max_tokens":24}'
```

The observed public route uses a ZeroSSL certificate; standard current public CA trust works. Use a combined public/cluster trust bundle for clients that override their default CA store. For self-signed routes, add the current ingress CA. The API server CA and ingress CA may differ. The model's `LLMInferenceService.status.url` may report HTTP; use the HTTPS MaaS base URL and the fully qualified model ID for governed requests.

## Sources

- [OpenShift AI 3.5 MaaS configuration](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/deploy-and-manage-models-as-a-service).
- [Red Hat AI Inference Server 3.3 CPU AVX2 serving](https://docs.redhat.com/en/documentation/red_hat_ai_inference_server/3.3/html-single/getting_started/getting_started#serving-and-inferencing-with-podman-using-cpu-x86-64-avx2_getting-started).
- [TinyLlama model card](https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0).

## Verified deployment (2026-11-23)

On OpenShift 4.22.22 with OpenShift AI 3.5.3, the AVX2 worker check loaded PyTorch and vLLM successfully. TinyLlama reached 2/2 containers Ready; the LLMInferenceService and MaaSModelRef became Ready; the access policy and both subscriptions became Active. Only the `aigateway` DSC component changed compared with the pre-install snapshot.

- MaaS base URL: `https://maas.apps.ocp.qmgmn.sandbox483.opentlc.com`.
- Chat endpoint: `https://maas.apps.ocp.qmgmn.sandbox483.opentlc.com/v1/chat/completions`.
- Public health endpoint returned HTTP 200.
- Anonymous model discovery returned HTTP 401.
- Free-bound and premium-bound temporary API keys each discovered only the selected subscription and completed a short chat request with HTTP 200. Each response reported 24 prompt and 24 completion tokens. Keys were revoked afterward and the temporary service account and CPU check pod were removed.
- Profile-linked resource values remain requests 4 CPU / 12 GiB, limits 6 CPU / 16 GiB, with zero GPU requests.

These were short operational checks, not load or throughput benchmarks. No recurring load job was created.
