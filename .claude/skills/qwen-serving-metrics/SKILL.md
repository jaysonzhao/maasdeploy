---
name: qwen-serving-metrics
description: Build, deploy, update, or troubleshoot this repository's standalone OpenShift app for comparing per-pod Qwen vLLM and llm-d TTFT P99 and KV prefix-cache hit rate. Use when changing the Qwen metrics dashboard, its Prometheus queries, or OpenShift exposure.
---

# Qwen Serving Metrics App

Use this project skill to maintain the standalone comparison app for the Qwen 2.5 7B vLLM and llm-d deployments. Work from the repository root and keep source, manifests, deployment behavior, and this guide aligned.

## Source of truth

| Purpose | Files |
|---|---|
| UI, 30-second polling, in-page trend charts | `apps/qwen-metrics/index.html`, `styles.css`, `app.js` |
| Prometheus query API | `apps/qwen-metrics/server.py` |
| Metric formulas and operator overview | `apps/qwen-metrics/README.md` |
| OAuth, Route, Deployment, ServiceAccount, and RBAC | `manifests/12-qwen-metrics-dashboard/` |
| Source ConfigMap, cookie Secret, apply, restart, and rollout | `scripts/deploy-qwen-metrics-dashboard.sh` |

The Python API uses only the standard library. Keep bearer tokens on the server; never send the ServiceAccount token or a MaaS model API key to browser JavaScript.

## Metric behavior

The app displays each pod separately:

- **TTFT P99:** `histogram_quantile(0.99, sum by (le, pod) (rate(kserve_vllm:time_to_first_token_seconds_bucket{...}[5m])))`.
- **KV prefix-cache hit rate:** per-pod `rate(prefix_cache_hits_total[5m]) / rate(prefix_cache_queries_total[5m])`, shown as a percentage.
- The page queries immediately on load and every 30 seconds. Each value represents a rolling five-minute window. Trend history accumulates in the open browser tab and resets when the page is reloaded.
- Return an empty value when the metric has no recent series or the cache-query denominator is zero. Do not display missing data as a measured zero.

The current cluster's vLLM scrape labels are `namespace` and `pod`; it does not expose `exported_namespace` and `k8s_pod_name`. Before reusing the app on another cluster or RHOAI version, inspect the live series labels. Adapt selector and grouping labels to the collected series while retaining per-pod grouping and the formulas above. Keep the selectors constrained to the intended namespace and the two Qwen deployment names. The `-vll-kserve-` pod name identifies vLLM; the base `-kserve-` pod name identifies llm-d.

For example, on the current cluster the selector is:

```promql
namespace="llm",model_name=~"redhataiqwen25-7b-instruct(-vll)?",pod=~"redhataiqwen25-7b-instruct(-vll)?-kserve-.*"
```

## OpenShift access model

- The browser reaches the app through an HTTPS Route and OpenShift OAuth proxy.
- The app ServiceAccount queries the project-scoped Thanos Querier API at `https://thanos-querier.openshift-monitoring.svc:9092` with `namespace=llm` and has the `view` ClusterRole bound only in the `llm` namespace.
- The injected OpenShift service CA validates the internal Thanos TLS certificate. Preserve the CA mount and the projected ServiceAccount token.
- Preserve the `system:auth-delegator` ClusterRoleBinding, the OAuth service authorization check, the serving-certificate annotation, and cookie Secret. Keep cookie values out of Git and command output.
- Keep route hostnames out of source and manifests; read the created host from the Route after deployment.

## Deploy or update

Check the selected cluster before applying resources:

```bash
pwd
oc whoami --show-server
oc whoami
```

Deploy or update from the repository root:

```bash
./scripts/deploy-qwen-metrics-dashboard.sh
```

The script checks the `oc` login, creates the dedicated namespace, updates the source ConfigMap, preserves an existing OAuth cookie Secret, applies the Kustomize resources, restarts the app, waits for rollout, and prints the HTTPS Route. The deployment is isolated in `qwen-metrics-dashboard`; do not apply it in `llm`.

## Verify

Run source and manifest checks before deployment:

```bash
python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("apps/qwen-metrics/server.py").read_text())'
node --check apps/qwen-metrics/app.js
bash -n scripts/deploy-qwen-metrics-dashboard.sh
oc kustomize manifests/12-qwen-metrics-dashboard >/dev/null
git diff --check
```

After rollout, confirm the ready pod and its API response:

```bash
oc rollout status deployment/qwen-metrics-dashboard -n qwen-metrics-dashboard
POD="$(oc get pods -n qwen-metrics-dashboard -l app.kubernetes.io/name=qwen-metrics-dashboard --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
oc exec "$POD" -n qwen-metrics-dashboard -c app -- python3 -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8080/api/metrics', timeout=30).read().decode())"
oc get route qwen-metrics-dashboard -n qwen-metrics-dashboard
```

Check for both engine names and each active replica in the JSON. If the response has no pods, query the metrics without pod-label filters to inspect actual label names and confirm the current pod names. If the API returns 502, inspect app logs, the service-CA ConfigMap, the Thanos endpoint, and the ServiceAccount RoleBinding in `llm`. Do not broaden the RoleBinding beyond the metrics namespace to work around a query error.

## References

- [OpenShift AI 3.5 llm-d monitoring](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/monitoring-llmd-deployments)
- [OpenShift monitoring APIs](https://docs.redhat.com/en/documentation/monitoring_stack_for_red_hat_openshift/4.21/html/accessing_metrics/accessing-monitoring-apis-by-using-the-cli)
- [vLLM metrics](https://docs.vllm.ai/en/latest/usage/metrics/)
