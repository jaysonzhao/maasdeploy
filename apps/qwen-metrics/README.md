# Qwen serving metrics app

This standalone OpenShift app compares the per-pod TTFT P99 and KV prefix-cache hit rate of the Qwen 2.5 7B vLLM and llm-d deployments. The page polls every 30 seconds and charts a rolling in-browser history for up to 15 minutes after it is opened.

See [the repository skill](../../.claude/skills/qwen-serving-metrics/SKILL.md) for the deployment, security, and verification workflow.

## Deploy

Log in to the target cluster, then run from the repository root:

```bash
./scripts/deploy-qwen-metrics-dashboard.sh
```

The script prints the HTTPS Route when the Deployment is ready. OpenShift OAuth protects the page. The app ServiceAccount has the `view` role in the `llm` namespace and queries the project-scoped Thanos Querier API. It does not store a cluster token or model API key in the repository.

## Metrics

Both queries use the last five minutes and select only the two Qwen deployments in namespace `llm`. This cluster's collected series use `namespace` and `pod` labels (the example expressions using `exported_namespace` and `k8s_pod_name` refer to a different label set):

```promql
histogram_quantile(
  0.99,
  sum by (le, pod) (
    rate(kserve_vllm:time_to_first_token_seconds_bucket{
      namespace="llm",
      model_name=~"redhataiqwen25-7b-instruct(-vll)?",
      pod=~"redhataiqwen25-7b-instruct(-vll)?-kserve-.*"
    }[5m])
  )
)
```

```promql
sum by (pod) (
  rate(kserve_vllm:prefix_cache_hits_total{
    namespace="llm",
    model_name=~"redhataiqwen25-7b-instruct(-vll)?",
    pod=~"redhataiqwen25-7b-instruct(-vll)?-kserve-.*"
  }[5m])
)
/
sum by (pod) (
  rate(kserve_vllm:prefix_cache_queries_total{
    namespace="llm",
    model_name=~"redhataiqwen25-7b-instruct(-vll)?",
    pod=~"redhataiqwen25-7b-instruct(-vll)?-kserve-.*"
  }[5m])
)
```

The app converts the hit ratio to a percentage for display. It leaves a metric blank when the series has no recent samples or its query denominator is zero. The trend lines live in the open browser tab and reset when the page is reloaded.
