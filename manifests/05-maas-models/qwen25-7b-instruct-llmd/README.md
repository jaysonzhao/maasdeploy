# RedHatAI/Qwen2.5-7B-Instruct with llm-d

This folder consolidates the desired-state YAML for the llm-d-backed Qwen 2.5 7B deployment observed in project `llm`. The separate `redhataiqwen25-7b-instruct-vll` single-node vLLM deployment is not included.

## Deploy

After confirming the target cluster and the prerequisites below, apply the bundle:

```bash
oc apply -k manifests/05-maas-models/qwen25-7b-instruct-llmd
```

The bundle contains the `LLMInferenceService` and its MaaS model reference. RHOAI/KServe and the llm-d integration reconcile the workload Deployment, router scheduler Deployment, InferencePool, Endpoint Picker and workload Services, and HTTPRoute. Those generated objects are intentionally not included as apply-ready YAML because their owner is the `LLMInferenceService` controller.

## Prerequisites

- OpenShift AI/KServe must serve `serving.kserve.io/v1alpha2` `LLMInferenceService` resources and support the llm-d router scheduler fields used here.
- The `llm` namespace must exist with `opendatahub.io/generated-namespace=true`, `maas.opendatahub.io/gateway-access=true`, and `opendatahub.io/dashboard=true` for MaaS, model serving, and dashboard discovery.
- The `maas-default-gateway` Gateway must exist in `openshift-ingress`, with the installed Gateway API and InferencePool APIs compatible with the cluster's KServe release.
- The shared `l40s-shared` hardware profile must exist in `redhat-ods-applications`. The target node needs NVIDIA L40S time slicing, the `nvidia.com/device-plugin.config=NVIDIA-L40S` and `nvidia.com/gpu.present=true` labels, and the `maas.opendatahub.io/qwen-pair=true` placement label.
- The model connection Secret referenced by `opendatahub.io/connections` must exist in `llm`. The Secret content is intentionally excluded from Git; recreate or select the model connection in the dashboard and update the reference for another cluster.
- The LLMInferenceService uses the RHOAI 3.5 llm-d presets in `redhat-ods-applications`; this bundle does not copy or change those shared presets, hardware profiles, Gateway, or namespace configuration.

## Captured settings

- Model artifact: `oci://registry.redhat.io/rhelai1/modelcar-qwen2-5-7b-instruct:1.5`.
- Two replicas request one logical `nvidia.com/gpu` share each and target the labeled L40S node pool.
- vLLM arguments preserve the observed values: GPU memory utilization `0.84`, maximum model length `32768`, and KV cache cap `2684354560` bytes.
- GPU time slicing shares scheduling capacity; it does not partition or reserve GPU memory. Treat the vLLM memory settings as an observed configuration, not a guarantee that both replicas fit together.

This is a desired-state bundle. Check live `LLMInferenceService` and pod readiness after applying; controller status and generated resources are not embedded in these manifests.
