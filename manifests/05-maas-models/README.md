# Phase 5: MaaS Model Deployment

Deploy and register LLM models with the MaaS platform.

Full documentation: https://rh-aiservices-bu.github.io/rhoai-maas-guide/modules/main/05-maas-models.html

## Direct vLLM deployment on a shared L40S

The [`nemotron-safety-guard-vllm/`](nemotron-safety-guard-vllm/) Kustomize directory captures the cluster-specific `nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3` Deployment and its 30 GiB Hugging Face cache PVC in namespace `llm`. It requests one logical `nvidia.com/gpu` share from the NVIDIA-L40S time-sliced device-plugin profile and uses required pod affinity to share a node with the existing Qwen vLLM deployment.

Deploy or reconcile it with:

```bash
./scripts/deploy-nemotron-safety-guard-vllm.sh
```

The target cluster must already have L40S time slicing configured and the matching Qwen vLLM pods Ready. `--gpu-memory-utilization=0.48` is a vLLM allocation target, not a GPU memory reservation. NVIDIA time slicing does not isolate VRAM; inspect current GPU memory use before adding or restarting workloads. This standalone Deployment does not create a Service, Route, `MaaSModelRef`, or MaaS subscription.

## Qwen 2.5 7B Instruct: llm-d and single-node vLLM

The [`qwen25-7b-instruct/`](qwen25-7b-instruct/) folder keeps both two-replica `RedHatAI/Qwen2.5-7B-Instruct` deployments and their MaaS model references together. It includes the llm-d router/scheduler configuration and the single-node vLLM configuration, including its `LLMInferenceServiceConfig`.

Use the end-to-end setup script to deploy one path or both:

```bash
./scripts/setup-maas.sh --from-phase 5 --model qwen-llmd --skip-verify
./scripts/setup-maas.sh --from-phase 5 --model qwen-vllm --skip-verify
./scripts/setup-maas.sh --from-phase 5 --model qwen-pair --skip-verify
```

The Qwen choices are applied even when another `LLMInferenceService` already exists in `llm`. `qwen-pair` applies both configurations together. For a direct Kustomize apply, use `oc apply -k manifests/05-maas-models/qwen25-7b-instruct/`; use the `llm-d/` or `vllm/` subfolder to apply one path.

Review the folder README for cluster prerequisites, Secret references, and the captured resource settings. NVIDIA time slicing allocates logical GPU shares; it does not partition or reserve VRAM. The bundle contains desired-state CRs, not controller-generated Deployments, Services, InferencePools, or HTTPRoutes. MaaS authorization policies and subscriptions remain separate governance resources.
