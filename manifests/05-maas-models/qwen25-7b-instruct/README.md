# RedHatAI/Qwen2.5-7B-Instruct: llm-d and vLLM

This folder groups the two observed `LLMInferenceService` configurations in project `llm` for the same Qwen 2.5 7B model:

- `llm-d/` deploys `redhataiqwen25-7b-instruct` through the llm-d router and scheduler.
- `vllm/` deploys the Kubernetes resource `redhataiqwen25-7b-instruct-vll` through single-node vLLM. The OpenShift AI display name is `redhataiqwen25-7b-instruct-vllm`. Its bundle includes the referenced `LLMInferenceServiceConfig`.
- The root Kustomization applies both variants.

## Deploy

The repository setup script can deploy either serving path or both. It applies the selected Qwen resources even if other models already exist in `llm`:

```bash
./scripts/setup-maas.sh --from-phase 5 --model qwen-llmd --skip-verify
./scripts/setup-maas.sh --from-phase 5 --model qwen-vllm --skip-verify
./scripts/setup-maas.sh --from-phase 5 --model qwen-pair --skip-verify
```

The standalone model script accepts the same values:

```bash
./scripts/deploy-model.sh --model qwen-pair
```

For direct Kustomize use, apply the root directory for both models or a subdirectory for one:

```bash
oc apply -k manifests/05-maas-models/qwen25-7b-instruct/
oc apply -k manifests/05-maas-models/qwen25-7b-instruct/llm-d/
oc apply -k manifests/05-maas-models/qwen25-7b-instruct/vllm/
```

## Prerequisites

- OpenShift AI/KServe must serve `serving.kserve.io/v1alpha2` `LLMInferenceService` resources. The llm-d variant also needs compatible llm-d scheduler/router support.
- The `llm` namespace must exist and have the `opendatahub.io/generated-namespace=true`, `maas.opendatahub.io/gateway-access=true`, and `opendatahub.io/dashboard=true` labels. The setup scripts add these labels.
- The `maas-default-gateway` Gateway must exist in `openshift-ingress`.
- The shared `l40s-shared` hardware profile must exist in `redhat-ods-applications`; the target node must have NVIDIA L40S time slicing and the matching `nvidia.com/device-plugin.config=NVIDIA-L40S` and `nvidia.com/gpu.present=true` labels. The llm-d deployment additionally selects `maas.opendatahub.io/qwen-pair=true`.
- Both LLMInferenceServices reference model-connection Secrets in `llm`: `secret-yqrd37` for llm-d and `secret-yi3ywx` for vLLM. The secret values are not in this repository. For another cluster, create/select the appropriate connection and update the reference name if needed.
- The llm-d service uses the RHOAI 3.5 llm-d presets in `redhat-ods-applications`. These shared presets, the hardware profile, namespace, and Gateway are not managed by this bundle.

## Captured settings

Both model services use the same OCI model artifact and request two replicas, each with `2` CPUs, a `4Gi` memory request, a `36Gi` memory limit, and one logical `nvidia.com/gpu` share.

| Serving path | Resource name | vLLM arguments | Placement |
|---|---|---|---|
| llm-d | `redhataiqwen25-7b-instruct` | `--gpu-memory-utilization=0.84 --max-model-len=32768 --kv-cache-memory-bytes=2684354560` | NVIDIA L40S plus `maas.opendatahub.io/qwen-pair=true` |
| Single-node vLLM | `redhataiqwen25-7b-instruct-vll` | `--gpu-memory-utilization=0.45 --max-model-len=32768 --kv-cache-memory-bytes=2684354560` | NVIDIA L40S |

These are captured deployment settings, not a GPU memory guarantee. Time slicing allows multiple workloads to share GPU scheduling capacity; it does not partition VRAM. The values above do not reserve GPU memory, so inspect the physical L40S's available memory before deploying both variants or restarting workloads.

The manifests contain desired-state CRs only. KServe/RHOAI creates the workload Deployments and Services; llm-d controllers also create the scheduler, InferencePool, endpoint picker and related Services, and routing resources. Generated status, UIDs, resource versions, and controller-owned objects are omitted. MaaS authorization policies and subscriptions remain independent governance resources and are not changed by these manifests.

## Verify

```bash
oc get llminferenceservice -n llm
oc get maasmodelref -n llm
oc get pods -n llm -o wide
```

Check the `Ready` condition for each selected `LLMInferenceService` and its matching `MaaSModelRef`. Verify both replicas schedule to the intended L40S node. The setup scripts wait for the selected service and reference readiness for up to ten minutes and print their status if either remains unavailable.
