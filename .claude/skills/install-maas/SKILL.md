---
name: install-maas
description: Deploy, resume, verify, observe, or remove Red Hat OpenShift AI Models as a Service (MaaS) resources using this repository's scripts and manifests.
argument-hint: "[--model simulator|granite-tiny-gpu|gpt-oss-20b|auto] [--from-phase N] [--with-observability] [--with-external-models] [--with-mlflow]"
allowed-tools: Bash(oc *), Bash(./*), Bash(envsubst *), Bash(curl *), Bash(jq *), Bash(grep *), Bash(ls *), Bash(cat *), Bash(date *), Bash(mkdir *), Bash(echo *), Bash(bash *), AskUserQuestion
---

# Deploy and Operate MaaS on OpenShift

Use this skill for the complete lifecycle in this repository: cluster preparation, MaaS installation, model deployment, dashboard telemetry, external models, verification, recurring rate-limit load, troubleshooting, and load-test cleanup.

## Source of truth

Run commands from the repository root. `scripts/setup-maas.sh` is the end-to-end orchestrator; its options and phase implementation take precedence over older phase tables in docs. Use the phase runbooks and manifests when a manual step or deeper explanation is needed:

| Area | Source |
|---|---|
| End-to-end deployment | `scripts/setup-maas.sh` |
| Phases 1–2: operators and platform | `manifests/01-prerequisites/`, `manifests/02-platform-config/`; `content/modules/ROOT/pages/01-prerequisites.adoc`, `02-platform-config.adoc` |
| Phases 3–4: MaaS database and RHOAI | `manifests/03-maas-platform/`, `manifests/04-rhoai-config/`; matching `03-maas-platform.adoc` and `04-rhoai-config.adoc` |
| Phase 5: local model | `scripts/deploy-model.sh`, `manifests/05-maas-models/`, `05-maas-models.adoc` |
| Phase 6: verification | `scripts/verify-maas.sh`, `manifests/06-verification/verify.sh`, `06-verification.adoc` |
| Phase 7: observability and MaaS usage dashboard | `manifests/07-observability/`, `07-observability.adoc` |
| Phase 8: external model providers | `manifests/08-external-models/`, `08-external-models.adoc` |
| Phase 9: MLflow experiment tracking | `manifests/10-mlflow/mlflow.yaml`, `10-mlflow.adoc` |
| 20-minute free/premium load demo | `scripts/run-maas-loadtest.sh`, `scripts/cleanup-maas-loadtest.sh`, `manifests/09-load-test/`, `09-load-test.adoc` |
| Guided MaaS access portal | `portal/`, `scripts/deploy-maas-portal.sh`, `manifests/11-maas-portal/`, `11-maas-portal.adoc` |

## Safety and cluster selection

Before any `oc apply`, patch, or delete:

1. Check the repository root and the selected context: `pwd`, `oc whoami --show-server`, and `oc whoami`.
2. If the logged-in server is not the cluster the user named, stop and log in to the requested API endpoint. Never infer a target cluster from a previously used context.
3. The full install is cluster-wide and requires an authorized cluster-admin identity. `oc login --token="$OCP_TOKEN" --server="https://api.<cluster-domain>:6443"` accepts a token from the environment.
4. Never put passwords, OpenShift tokens, MaaS API keys, or third-party provider keys in the skill, manifests, Git, command output, or final response. Do not echo them. Prefer a protected environment variable or prompt-based secret input; the external-provider script accepts `EXTERNAL_MODEL_API_KEY`.

The install modifies cluster-scoped operators, monitoring configuration, gateways, and RHOAI resources. The recurring demo creates regular MaaS API keys and a CronJob. Run destructive cleanup only when the user asks to remove the demo or it is clearly part of their requested task.

## Full installation

Check available script options first when details may have changed:

```bash
./scripts/setup-maas.sh --help
```

The script checks the current `oc` login, discovers the cluster domain and MaaS API namespace, detects installed components, and runs the requested phases. Re-running is designed to skip components already detected as ready.

Recommended CPU-only demo:

```bash
./scripts/setup-maas.sh --model simulator --with-observability
```

For GPU clusters, use `--model auto` (the default) or select a model explicitly:

- `simulator`: CPU-only validation and demos.
- `granite-tiny-gpu`: smaller GPU workload.
- `gpt-oss-20b`: larger GPU workload.
- `auto`: select based on detected GPU capacity; falls back to the simulator if no GPU is found.

The script phases are:

| Phase | Work |
|---|---|
| 0 | Preflight and cluster-state detection |
| 1 | RHOAI, connectivity-link, cert-manager, and LeaderWorkerSet operator subscriptions |
| 2 | Kuadrant/Authorino, User Workload Monitoring, GatewayClass, and Gateway configuration |
| 3 | MaaS PostgreSQL persistence, secrets, and platform resources |
| 4 | DSCI/DSC MaaS configuration, dashboard config, and `maas-api` readiness |
| 5 | Local model deployment and MaaS model/subscription resources |
| 6 | End-to-end API, authentication, inference, and rate-limit verification |
| 7 | Optional Tempo, OpenTelemetry, Cluster Observability Operator (COO), DSCI monitoring, dashboard flag, and tenant telemetry |
| 8 | Optional OpenAI, Gemini, or Bedrock external model setup |
| 9 | Optional RHOAI MLflow server with SQLite and a persistent test volume |

Common invocations:

```bash
# Preview a full run
./scripts/setup-maas.sh --dry-run --model simulator --with-observability

# Resume after a failure; earlier phases are skipped
./scripts/setup-maas.sh --from-phase 4 --model simulator

# Install only a local model on an existing MaaS platform
./scripts/setup-maas.sh --from-phase 5 --model simulator

# Verify an existing deployment
./scripts/setup-maas.sh --from-phase 6
# or
./scripts/verify-maas.sh

# Add/repair observability on an existing deployment, including the console flag
./scripts/setup-maas.sh --from-phase 7 --with-observability

# Enable the RHOAI MLflow experiment tracking server
./scripts/setup-maas.sh --from-phase 9 --with-mlflow
```

`--from-phase N` skips phases before `N`; it does not force earlier phases to run. `--skip-models` skips phase 5 and `--skip-verify` skips phase 6. Phase 7 only runs when `--with-observability` is supplied. Phase 8 only runs when `--with-external-models` is supplied. Phase 9 only runs when `--with-mlflow` is supplied.

## MLflow experiment tracking

RHOAI 3.5 dashboard visibility follows the `mlflowoperator` state in the DataScienceCluster; do not add the deprecated dashboard `mlflow` feature flag. Phase 4 already manages the operator. Phase 9 creates the cluster-scoped `MLflow/mlflow` resource from `manifests/10-mlflow/mlflow.yaml` and waits for `Available=True`.

The repository manifest is for development and test: one replica, SQLite metadata, a 10 GiB `ReadWriteOnce` volume, and local file artifact storage. The installed RHOAI 3.5 MLflow CRD requires `serveArtifacts: true` with a file artifact destination, while the Red Hat guide cautions that artifact serving with file storage and a PVC is unsupported. Treat it as a UI/tracking demo and use PostgreSQL plus S3-compatible storage from Secrets for production or dependable artifact transfer. For workbench integration, dashboard-managed notebooks receive the MLflow annotation automatically; GitOps-managed notebooks need `opendatahub.io/mlflow-instance: mlflow` and a restart. Read `content/modules/ROOT/pages/10-mlflow.adoc` before changing storage or notebook annotations.

## Manual deployment

Prefer `setup-maas.sh` for a complete deployment. If the user needs manual control, follow the same order and status gates in the phase docs: prerequisite operators → platform/Gateway → MaaS database/platform → DSCI/DSC → model → verification → optional observability → optional external model. Apply the matching repository Kustomize directory rather than copying old commands from chat history. Inspect each manifest and current cluster state before applying it.

For model-only changes, use:

```bash
./scripts/deploy-model.sh --help
./scripts/deploy-model.sh --model simulator
```

To publish the seven-step MaaS guided journey behind OpenShift OAuth, first check the selected cluster, then run:

```bash
oc whoami --show-server
./scripts/deploy-maas-portal.sh
```

The portal serves static feature descriptions and links only. It does not read cluster objects or accept API keys. Use `.claude/skills/build-maas-portal/SKILL.md` for portal-specific build, contextual link, and verification instructions; read `content/modules/ROOT/pages/11-maas-portal.adoc` for the deployment and cleanup runbook.

Check model readiness and the MaaS catalog:

```bash
oc get maasmodelref -n llm
oc get maassubscription -n models-as-a-service
```

## Add a vLLM deployment that shares a time-sliced GPU

Use this workflow on RHOAI 3.5 when adding a basic vLLM deployment to MaaS alongside an existing model. Give the new deployment a unique name; leave the existing `LLMInferenceService` and its replicas unchanged. The validated example below runs two replicas of `RedHatAI/Qwen2.5-7B-Instruct` on one NVIDIA L40S, with each replica requesting one logical GPU share.

NVIDIA GPU Operator time slicing schedules multiple pods against one physical GPU. It does not partition GPU memory or provide memory/fault isolation between the replicas, so competing workloads can reduce throughput or cause out-of-memory failures. Configure and verify time slicing through the installed GPU Operator before deploying the model. Follow the [NVIDIA GPU Operator time-slicing guide](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/time-slicing-gpus-in-openshift.html) for the installed Operator version.

### Preconditions

1. Confirm the target cluster before changing dashboard or model resources: `oc whoami --show-server` and `oc whoami`.
2. Confirm RHOAI 3.5 and MaaS are Ready, and identify the target GPU node and its device-plugin configuration:

   ```bash
   oc get nodes -l nvidia.com/gpu.present=true -L nvidia.com/gpu.product,nvidia.com/gpu.replicas
   oc describe node <gpu-node> | grep -E 'nvidia.com/gpu'
   ```

   The selected node must advertise at least two schedulable GPU shares for a two-replica example. If the GPU Operator config uses `renameByDefault: true`, use the resulting shared resource name in the hardware profile; otherwise, the resource is typically `nvidia.com/gpu`.
3. In OpenShift AI **Settings → Hardware profiles**, select or create a profile that targets the intended GPU nodes and requests one logical GPU share per pod. Confirm project quota allows two replicas. A hardware profile sets scheduling/resource requests; it does not create GPU time slicing.
4. Keep each vLLM pod's host-memory request/limit and GPU cache settings within the capacity tested for the model and runtime. Time slicing does not reserve a fraction of GPU memory for each pod.

### Enable vLLM on MaaS

In RHOAI 3.5, dashboard-created vLLM-on-MaaS deployments are a Technology Preview feature. Enable the feature flag only on clusters where that preview is appropriate. Check the current value, then merge the flag without replacing other dashboard settings:

```bash
oc get odhdashboardconfig odh-dashboard-config -n redhat-ods-applications \
  -o jsonpath='{.spec.dashboardConfig.vLLMDeploymentOnMaaS}{"\n"}'

oc patch odhdashboardconfig odh-dashboard-config -n redhat-ods-applications \
  --type=merge \
  -p '{"spec":{"dashboardConfig":{"vLLMDeploymentOnMaaS":true}}}'
```

Wait for the dashboard configuration to reconcile, then reload the OpenShift AI dashboard. See [RHOAI 3.5 dashboard configuration](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/managing_resources/customizing-the-dashboard) and [model-serving configuration](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/configuring_your_model-serving_platform/configuring-model-servers_rhoai-admin).

### Deploy the additional model

In the OpenShift AI dashboard, choose the model catalog entry or approved model artifact and deploy it in the intended project. In the wizard:

1. Choose the **vLLM on MaaS** / basic vLLM deployment path and an enabled single-node `LLMInferenceServiceConfig`. Do not choose **Distributed inference with llm-d** for this configuration. If the single-node config is unavailable, check the enabled LLM accelerator configurations under **Settings → Model resources and operations**.
2. Select the shared-GPU hardware profile. Set replicas to `2`; each replica should request one logical GPU share. Review the generated YAML and make sure the new resource name is unique so the existing deployment is not edited or replaced.
3. Enable MaaS publication. After deployment, confirm the generated `MaaSModelRef` points to the new `LLMInferenceService`.
4. Add the new model reference only to the intended `MaaSSubscription` and matching `MaaSAuthPolicy`. For example, if this model is meant for the premium audience, update that subscription and policy; do not grant access through a free subscription unless requested. Both resources must include the model reference: the subscription sets the token quota and the authorization policy grants gateway access. Inspect the installed CRD schema and preserve existing entries when editing either resource.

The validated Qwen 2.5 7B example used the model artifact `oci://registry.redhat.io/rhelai1/modelcar-qwen2-5-7b-instruct:1.5`, two replicas, one GPU share per replica, 2 CPU cores, 4 GiB memory request, and 36 GiB memory limit per pod. With vLLM runtime `0.24.0+rhaiv.13`, these additional arguments were used to bound the cache and context size:

```text
--gpu-memory-utilization=0.84 --max-model-len=32768 --kv-cache-memory-bytes=2684354560
```

Treat these as a tested example for that model/runtime combination, not universal settings. Re-check available GPU memory, runtime support for `--kv-cache-memory-bytes`, model context requirements, and the other workloads on the physical card before reusing them.

### Verify deployment and access

```bash
oc get llminferenceservice -n <model-namespace>
oc get pods -n <model-namespace> -o wide
oc get maasmodelref -n <model-namespace>
oc get maassubscription -n models-as-a-service
oc get maasauthpolicy -n models-as-a-service
```

Confirm the new `LLMInferenceService` is Ready, both new pods are Ready and scheduled to the intended shared-GPU node, and the original deployment remains Ready with its original replica count. Confirm the new `MaaSModelRef` is Ready and included in the intended subscription and authorization policy. The OpenShift AI dashboard's **Gen AI studio → AI asset endpoints** page should list the model as Ready and show the MaaS endpoint. A successful pod deployment by itself does not prove that subscription quota and authorization are configured correctly.

For the RHOAI 3.5 publication, subscription, and authorization workflow, see [Govern LLM access with MaaS](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/index).

## MaaS usage dashboard and telemetry

The OpenShift AI Observability Dashboard needs the monitoring stack and the dashboard feature flag. Phase 7 configures DSCI monitoring, enables `OdhDashboardConfig.spec.dashboardConfig.observabilityDashboard`, turns on default tenant usage telemetry, and waits for operator-created gateway telemetry (using repository telemetry manifests as a fallback). Phase 4 also applies the dashboard configuration so a phase resume does not silently omit its UI flag.

Use the tenant kind present on the cluster: RHOAI 3.5+ uses `MaasTenantConfig`; RHOAI 3.4 uses `Tenant`. The setup script detects the resource. Do not patch a `Tenant` on a cluster that has `MaasTenantConfig`.

For a missing dashboard or missing MaaS usage data:

1. Run `./scripts/setup-maas.sh --from-phase 7 --with-observability`.
2. Check DSCI readiness and monitoring configuration: `oc get dsci default-dsci -o yaml`.
3. Check the console flag: `oc get odhdashboardconfig odh-dashboard-config -n redhat-ods-applications -o jsonpath='{.spec.dashboardConfig.observabilityDashboard}{"\n"}'` (expect `true`).
4. Check the correct `default-tenant` telemetry resource in `models-as-a-service`, Perses dashboards in `redhat-ods-monitoring`, and gateway TelemetryPolicy resources in `openshift-ingress`.
5. Generate inference traffic and allow Prometheus to scrape the metrics. A dashboard resource can exist before it has data.

See `content/modules/ROOT/pages/07-observability.adoc` for version-specific checks and manual repair commands.

## External model providers

External providers require a working MaaS deployment and provider credentials. Store the credential only in the provider Secret created by the setup script; never commit it. Populate `EXTERNAL_MODEL_API_KEY` from an approved secret store without displaying it, then run:

```bash
./scripts/setup-maas.sh --from-phase 8 --with-external-models --external-model-provider openai
unset EXTERNAL_MODEL_API_KEY
```

Supported provider names are `openai`, `gemini`, and `bedrock`; OpenAI is the default. Check the external-model runbook before deploying a provider. It documents current provider routing caveats, including Gemini registration/inference limitations and Bedrock's requirement for a Bedrock API key and Mantle endpoint.

## Recurring free/premium rate-limit workload

Use this after a local MaaS model and both subscription tiers are Ready. The script defaults to model ref `gpt-oss-20b`; set the model ref and subscription names for other models. The repository's simulator example is:

```bash
MAAS_MODEL_REF=facebook-opt-125m-simulated \
MAAS_FREE_SUBSCRIPTION=simulator-free \
MAAS_PREMIUM_SUBSCRIPTION=simulator-premium \
./scripts/run-maas-loadtest.sh
```

The script creates regular API keys for the free and premium subscriptions, stores them in the `maas-load-test` namespace Secret, and installs `maas-rate-limit-demo`, scheduled every 20 minutes. The default key lifetime is 2160 hours (90 days). Each job runs both tiers concurrently for 180 seconds by default, uses up to eight in-flight requests per client, and keeps jobs from overlapping (`concurrencyPolicy: Forbid`). Model discovery retries transient network errors and HTTP 5xx responses up to three times before failing. The bounded requests are intended to show free-tier `429` responses while premium requests continue succeeding.

Supported overrides are read from `scripts/run-maas-loadtest.sh`: `MAAS_MODEL_REF`, `MAAS_MODEL`, `MAAS_FREE_SUBSCRIPTION`, `MAAS_PREMIUM_SUBSCRIPTION`, `MAAS_DURATION_SECONDS` (1–240 seconds), `MAAS_API_KEY_TTL`, `MAAS_INTERVAL_SECONDS`, `MAAS_MAX_TOKENS` (1–4096), `MAAS_REQUEST_TIMEOUT_SECONDS` (1–300), `MAAS_CONCURRENCY` (1–8), `MAAS_BASE_URL`, and `MAAS_VERIFY_TLS`. TLS verification is on by default; disable it only for an untrusted sandbox certificate when needed.

Inspect scheduled jobs and per-tier results:

```bash
oc get cronjob,job,pod -n maas-load-test
oc logs -f -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c free-tier
oc logs -f -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c premium-tier
```

Summaries distinguish completed successes, `429`s, incomplete `200` responses, and other HTTP statuses. `401`/`403` usually indicate key or subscription issues. If a prior Secret exists, the setup script refuses to replace it; use the cleanup script, then recreate the CronJob to rotate keys. To stop and clean up the demo:

```bash
./scripts/cleanup-maas-loadtest.sh
```

Cleanup attempts to revoke both API keys and removes the CronJob, Secret, ConfigMaps, Jobs, logs, and namespace. If revocation fails, the keys expire after their configured lifetime.

## Troubleshooting and handoff

Start with current resource state, events, and the failing phase. Useful checks include:

```bash
oc get csv -A
oc get pods -A
oc get gateway -A
oc get datasciencecluster default-dsc -o yaml
oc get deployment maas-api -A
oc get maasmodelref -A
```

Use `oc describe` and namespace events for a specific resource; avoid dumping Secret data. For the Gateway, MaaS API readiness, model readiness, verification failures, and observability cascades, use the troubleshooting section in the matching phase page. After work, report the target API server, model/provider deployed, phases run, verification result, dashboard/telemetry status, and whether the load CronJob is active or cleaned up. Never include credential values.
