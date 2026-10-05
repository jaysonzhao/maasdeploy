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
