#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${REPO_ROOT}/manifests/05-maas-models/nemotron-safety-guard-vllm"
NAMESPACE="llm"
QWEN_SELECTOR='app.kubernetes.io/name=redhataiqwen25-7b-instruct-vll'
NEMOTRON_SELECTOR='app.kubernetes.io/name=nemotron-safety-guard-vllm'

if ! command -v oc >/dev/null 2>&1; then
    echo "Required command not found: oc" >&2
    exit 1
fi

if ! oc whoami >/dev/null 2>&1; then
    echo "Log in to the target OpenShift cluster before deploying Nemotron Safety Guard." >&2
    exit 1
fi

echo "Connected to $(oc whoami --show-server) as $(oc whoami)."

if ! oc get nodes \
    -l nvidia.com/device-plugin.config=NVIDIA-L40S,nvidia.com/gpu.present=true \
    -o name | grep -q .; then
    echo "No L40S nodes with the NVIDIA-L40S shared device-plugin configuration were found." >&2
    exit 1
fi

echo "Waiting for the Qwen vLLM pods required by Nemotron's same-node placement rule."
oc wait --for=condition=Ready pod -l "${QWEN_SELECTOR}" -n "${NAMESPACE}" --timeout=600s

echo "Applying the Nemotron Safety Guard model cache and Deployment to ${NAMESPACE}."
oc apply -k "${MANIFEST_DIR}"
oc rollout status deployment/nemotron-safety-guard-vllm -n "${NAMESPACE}" --timeout=600s
oc get pods -n "${NAMESPACE}" -l "${NEMOTRON_SELECTOR}" -o wide

echo "The vLLM model ID is nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3."
echo "This deployment does not create a Service, Route, MaaSModelRef, or MaaS subscription."
