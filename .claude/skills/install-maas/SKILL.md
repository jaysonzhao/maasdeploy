---
name: install-maas
description: Deploy, resume, verify, observe, or remove Red Hat OpenShift AI Models as a Service (MaaS) resources using this repository's scripts and manifests.
argument-hint: "[--model simulator|granite-tiny-gpu|gpt-oss-20b|auto] [--from-phase N] [--with-observability] [--with-external-models]"
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
| Five-minute free/premium load demo | `scripts/run-maas-loadtest.sh`, `scripts/cleanup-maas-loadtest.sh`, `manifests/09-load-test/`, `09-load-test.adoc` |

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
```

`--from-phase N` skips phases before `N`; it does not force earlier phases to run. `--skip-models` skips phase 5 and `--skip-verify` skips phase 6. Phase 7 only runs when `--with-observability` is supplied. Phase 8 only runs when `--with-external-models` is supplied.

## Manual deployment

Prefer `setup-maas.sh` for a complete deployment. If the user needs manual control, follow the same order and status gates in the phase docs: prerequisite operators → platform/Gateway → MaaS database/platform → DSCI/DSC → model → verification → optional observability → optional external model. Apply the matching repository Kustomize directory rather than copying old commands from chat history. Inspect each manifest and current cluster state before applying it.

For model-only changes, use:

```bash
./scripts/deploy-model.sh --help
./scripts/deploy-model.sh --model simulator
```

Check model readiness and the MaaS catalog:

```bash
oc get maasmodelref -n llm
oc get maassubscription -n models-as-a-service
```

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

The script creates regular API keys for the free and premium subscriptions, stores them in the `maas-load-test` namespace Secret, and installs `maas-rate-limit-demo`, scheduled every five minutes. The default key lifetime is 2160 hours (90 days). Each job runs both tiers concurrently for 180 seconds by default, uses up to eight in-flight requests per client, and keeps jobs from overlapping (`concurrencyPolicy: Forbid`). The bounded requests are intended to show free-tier `429` responses while premium requests continue succeeding.

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
