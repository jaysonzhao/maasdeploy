#!/usr/bin/env python3
"""Serve the Qwen metrics page and its Prometheus-backed API."""

import json
import math
import os
import ssl
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
THANOS_URL = os.environ.get(
    "THANOS_QUERY_URL", "https://thanos-querier.openshift-monitoring.svc:9092"
).rstrip("/")
TOKEN_PATH = os.environ.get(
    "KUBERNETES_TOKEN_FILE", "/var/run/secrets/kubernetes.io/serviceaccount/token"
)
CA_FILE = os.environ.get("THANOS_CA_FILE", "/etc/pki/openshift/service-ca.crt")
POD_FILTER = (
    'namespace="llm",'
    'model_name=~"redhataiqwen25-7b-instruct(-vll)?",'
    'pod=~"redhataiqwen25-7b-instruct(-vll)?-kserve-.*"'
)
METRICS = {
    "ttftP99Seconds": (
        "histogram_quantile(0.99, sum by (le, pod) "
        "(rate(kserve_vllm:time_to_first_token_seconds_bucket{%s}[5m])))"
        % POD_FILTER
    ),
    "kvCacheHitRatio": (
        "sum by (pod) "
        "(rate(kserve_vllm:prefix_cache_hits_total{%s}[5m])) / "
        "sum by (pod) "
        "(rate(kserve_vllm:prefix_cache_queries_total{%s}[5m]))"
        % (POD_FILTER, POD_FILTER)
    ),
}


def query_prometheus(expression):
    with open(TOKEN_PATH, "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()
    query = urlencode({"query": expression, "namespace": "llm"})
    request = Request(
        f"{THANOS_URL}/api/v1/query?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    context = ssl.create_default_context(cafile=CA_FILE if Path(CA_FILE).is_file() else None)
    with urlopen(request, timeout=12, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError("The metrics API returned an unsuccessful query.")
    return payload.get("data", {}).get("result", [])


def values_by_pod(results):
    values = {}
    for result in results:
        pod_name = result.get("metric", {}).get("pod")
        if not pod_name or "redhataiqwen25-7b-instruct" not in pod_name:
            continue
        try:
            value = float(result["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values[pod_name] = value
    return values


def load_metrics():
    metrics = {name: values_by_pod(query_prometheus(expression)) for name, expression in METRICS.items()}
    pod_names = sorted(set(metrics["ttftP99Seconds"]) | set(metrics["kvCacheHitRatio"]))
    pods = []
    for pod_name in pod_names:
        if "redhataiqwen25-7b-instruct-vll-kserve-" in pod_name:
            engine = "vllm"
        elif "redhataiqwen25-7b-instruct-kserve-" in pod_name:
            engine = "llmd"
        else:
            continue
        hit_ratio = metrics["kvCacheHitRatio"].get(pod_name)
        pods.append(
            {
                "podName": pod_name,
                "engine": engine,
                "ttftP99Seconds": metrics["ttftP99Seconds"].get(pod_name),
                "kvCacheHitPercent": hit_ratio * 100 if hit_ratio is not None else None,
            }
        )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "windowSeconds": 300,
        "refreshSeconds": 30,
        "pods": pods,
    }


class MetricsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib handler API
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if path == "/api/metrics":
            try:
                body = json.dumps(load_metrics(), separators=(",", ":")).encode("utf-8")
            except (OSError, HTTPError, URLError, TimeoutError, ssl.SSLError, RuntimeError) as error:
                print(f"metrics query failed: {type(error).__name__}: {error}", flush=True)
                self.send_json(502, {"error": "Could not read Qwen metrics from OpenShift monitoring."})
                return
            self.send_json(200, body)
            return
        return super().do_GET()

    def send_json(self, status, body):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):  # noqa: N802 - stdlib handler API
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; font-src 'self'; script-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
        )
        if self.path.split("?", 1)[0] in {"/", "/index.html", "/app.js", "/styles.css", "/api/metrics"}:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), MetricsHandler).serve_forever()
