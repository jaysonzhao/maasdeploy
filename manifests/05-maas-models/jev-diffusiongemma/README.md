# JEV-style decisions on DiffusionGemma FP8

An additive deployment of `RedHatAI/diffusiongemma-26B-A4B-it-FP8-dynamic`
with the vLLM structured decision adapter. `jev-latest` is a compatibility
API name, not TypeSafe AI's proprietary Jev weights. This example is experimental.

## Live validation status

On 2026-10-27 the FP8 engine and adapter reached Ready on L40S. The complete
test suite passed: three native urgent/routine/ambiguous cases, an authenticated
native HTTPS case, and an authenticated MaaS chat case. Each decision case
covered `noul`, `choice`, and `score`. Missing credentials returned 401,
malformed native input returned 422, and MaaS model discovery returned the
published model. The MaaS response included positive prompt-token usage.

The HTTP compatibility wrapper is active and verified end to end. Only the
decision container was restarted to activate it; the GPU engine and its cache
stayed running. See `evidence/test-results.json` for actual responses and
latencies, and `evidence/status.json` for live resource conditions.

## Reproducibility

- Model revision: `3b3dae4697494da5a290e9c0461954449e76c4f5`.
- Runtime: `registry.redhat.io/rhaii-preview/vllm-cuda-rhel9@sha256:24fccf947aa33857611efed0d57aead4efc525c78a882760db5229b702713a1a`.
- Catalog tag resolved: `diffusiongemma-jev-1790351898`, amd64.
- Adapter upstream revision: `e9757321527ca1ecd514c07c1418dd2c53da3d19`.
- Adapter SHA256: `7cd9aa0081090c064eaac28db0f54f812749eeb3ae787d7f7653d2e35d8a938f`.

The supplied deployment skill originally specified BF16. The user selected
FP8 because each cluster GPU worker has one L40S with approximately 45 GiB
visible VRAM. Two time-slice resources represent one physical card and cannot
combine GPU memory. This deployment targets the unused L40S worker
`ip-10-0-17-135.us-east-2.compute.internal`; update the node selector in both
`base/workload.yaml` and `image-check.yaml` when using another cluster.

The engine requests one logical GPU resource, 4 CPU and 40 GiB host memory,
with 6 CPU / 56 GiB limits. Its GPU utilization budget is 0.85, context is
8,192 tokens, concurrency is four sequences and decision canvas is 64 tokens.
The adapter requests no GPU. This allocation assumes no other model uses
the physical GPU; time slicing does not isolate VRAM. Inspect actual GPU
memory before sharing this worker with another workload.

### Storage fallback used on 2026-10-27

The EBS CSI provisioner had a stale leader lease and restarting provisioner
containers; `jev-model-cache` remained Pending. The deployment therefore uses
`overlays/ephemeral`, with an 80 GiB local `emptyDir` cache and a 40 GiB
ephemeral-storage request. The selected node had approximately 128 GiB free
before starting. Reproduce this mode with `./deploy.sh ephemeral`.
The base bundle retains its 120 GiB PVC configuration for use after storage
recovers. A replacement pod in ephemeral mode must download the model again.
No shared storage controller settings are changed by this bundle.

## Architecture

The ordinary Deployment has two containers: loopback-only vLLM on port 8000
and an authenticated decision adapter on port 8011. A 120 GiB RWO PVC holds
the model snapshot and caches. The model and adapter are foreground processes
under restricted SCC. No cluster-wide AI settings are required by this bundle.

The local API supports `/v1/systemone` with `noul`, `choice`, and `score`
questions. The adapter also accepts structured questions through an
OpenAI-shaped `/v1/chat/completions` request. The MaaS `ExternalModel`
integration uses this latter API, authenticates through a model-specific
`MaaSAuthPolicy`, and assigns the `jev-decisions` subscription to the
`jev-client` service account. It does not grant access to every cluster user.

The backend Service is reached through an authenticated edge-TLS Route for
the MaaS provider connection. Its random API key is stored in the
`jev-backend-key` Secret, with `API_KEY` for the adapter and `api-key` for
the provider credential injector. It is generated only when missing. No
credentials are checked into Git. HF credentials are unnecessary for the
selected public ungated FP8 revision.

## Deploy and validate

Run from this directory using the intended authenticated `oc` context:

```sh
./deploy.sh ephemeral
oc logs deployment/jev-diffusiongemma -n jev-maas -c vllm -f
oc rollout status deployment/jev-diffusiongemma -n jev-maas --timeout=60s
python3 test.py --direct-only --output=evidence/direct-results.json
oc apply -f route.yaml
oc apply -f maas.yaml
oc wait --for=condition=Ready maasmodelref/jev-latest -n jev-maas --timeout=120s
oc wait --for=condition=Ready maasauthpolicy/jev-access -n models-as-a-service --timeout=120s
oc wait --for=condition=Ready maassubscription/jev-decisions -n models-as-a-service --timeout=120s
python3 test.py
```

Image pulls, model downloads and kernel initialization can take several minutes.
The standalone compatibility Job and the workload init container require the
structured-read hooks before starting the model. Model health alone is not
proof of working decisions. The tests require real probability distributions
and read diagnostics, exercise urgent/routine/ambiguous inputs, reject malformed
requests, and verify missing credentials are rejected both directly and through
MaaS. The client creates a short-lived service-account token in memory and
terminates its temporary port-forward when finished. Test results contain only
synthetic examples and observed responses, never credentials.

MaaS chat requests use `model: jev-latest`, a system message containing the
question schema, and a user message containing JSON state. Use
`X-MaaS-Subscription: jev-decisions`. The test script provides a complete
request example. This decision adapter is not a general-purpose chatbot.

The MaaS resources use `inference.opendatahub.io/v1alpha1` ExternalProvider
and ExternalModel directly. Legacy `maas.opendatahub.io` ExternalModel
resources are auto-migrated on this cluster, and their custom port annotations
were not preserved in the provider. The validated provider uses the adapter's
HTTPS Route on port 443. No global gateway or OpenShift AI configuration is
patched. Update the provider endpoint in `maas.yaml` for another cluster.

`base/maas_server.py` wraps the unchanged vendor source to decode chunked HTTP
request bodies forwarded by MaaS. The original example reads only
`Content-Length`; without the wrapper, valid MaaS requests returned an empty-body
parse error. The wrapper also copies the engine's prompt-token count from the
decision diagnostics into OpenAI usage, replacing the example's hardcoded zero.
The end-to-end test requires a positive prompt-token count. A local framing
check covered valid chunk extensions/trailers and five malformed cases.

The provider credential must have label
`inference.llm-d.ai/ipp-managed=true`; the older BBR label alone is insufficient
for the current injector and caused a missing-credential HTTP 500 during setup.
`deploy.sh` applies the current label without printing credentials.

After changing a mounted ConfigMap or Secret, restart the workload and rerun
the tests. A full pod restart in ephemeral mode discards its model cache:

```sh
oc rollout restart deployment/jev-diffusiongemma -n jev-maas
```

Inspect failures with:

```sh
oc get pods,pvc,service -n jev-maas
oc get events -n jev-maas --sort-by=.lastTimestamp
oc logs job/jev-image-check -n jev-maas
oc logs deployment/jev-diffusiongemma -n jev-maas -c verify-image
oc logs deployment/jev-diffusiongemma -n jev-maas -c vllm --tail=100
oc logs deployment/jev-diffusiongemma -n jev-maas -c decision --tail=100
oc get externalmodel,maasmodelref,httproute -n jev-maas
```

The image contains `HF_HUB_OFFLINE=1` by default; this bundle explicitly sets
it to `0` for the initial download. Tokenizer loading uses the exact local
FP8 snapshot. Restore the prior image, adapter and model revision together
when rolling back. The Recreate strategy avoids simultaneous allocations
against the same RWO volume. Do not add replicas without a storage/GPU plan.

To stop serving while retaining the model cache and credentials:

```sh
oc scale deployment/jev-diffusiongemma -n jev-maas --replicas=0
```

For removal when requested, delete `maas.yaml` and the Deployment/Service.
Preserve the PVC and Secret unless their deletion is explicitly intended.

## Sources

- [Red Hat FP8 model card](https://huggingface.co/RedHatAI/diffusiongemma-26B-A4B-it-FP8-dynamic).
- [Red Hat decision-model article](https://developers.redhat.com/articles/2026/09/28/run-decision-model-vllm-and-red-hat-ai).
- [Selected Red Hat runtime](https://catalog.redhat.com/en/software/containers/rhaii-preview/vllm-cuda-rhel9/69a57f9826444ada528619ad?image=6ab6a6245f9a48159264bee8&architecture=amd64).
- [vLLM structured decision recipe](https://recipes.vllm.ai/Google/diffusiongemma-26B-A4B-it).
- [Pinned Apache-2.0 adapter](https://github.com/vllm-project/vllm/blob/e9757321527ca1ecd514c07c1418dd2c53da3d19/examples/features/structured_diffusion/structured_server.py).
