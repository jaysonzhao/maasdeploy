#!/usr/bin/env python3
"""Send bounded inference traffic and report MaaS rate-limit results."""

import json
import http.client
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
import ssl
import sys
import time
import urllib.error
import urllib.request


def setting(name, default):
    return os.environ.get(name, default)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"free", "premium"}:
        print("usage: runner.py free|premium", file=sys.stderr)
        return 2

    tier = sys.argv[1]
    base_url = setting("MAAS_BASE_URL", "").rstrip("/")
    api_key = setting("MAAS_API_KEY", "")
    model_ref = setting("MAAS_MODEL_REF", "")
    model_id_override = setting("MAAS_MODEL", "")
    if not base_url or not api_key or not model_ref:
        print("Missing MaaS endpoint, API key, or model configuration", file=sys.stderr)
        return 2

    duration = max(1, int(setting("MAAS_DURATION_SECONDS", "180")))
    interval = max(0.1, float(setting("MAAS_INTERVAL_SECONDS", "0.5")))
    max_tokens = max(1, int(setting("MAAS_MAX_TOKENS", "20")))
    timeout = max(1, int(setting("MAAS_REQUEST_TIMEOUT_SECONDS", "2")))
    concurrency = max(1, min(8, int(setting("MAAS_CONCURRENCY", "8"))))
    verify_tls = setting("MAAS_VERIFY_TLS", "true").lower() not in {"false", "0", "no"}
    request_context = None if verify_tls else ssl._create_unverified_context()
    models_request = urllib.request.Request(
        f"{base_url}/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(
            models_request, timeout=timeout, context=request_context
        ) as response:
            available_models = json.loads(response.read().decode("utf-8")).get("data") or []
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        http.client.HTTPException,
        TimeoutError,
        OSError,
        ValueError,
    ) as error:
        status = error.code if isinstance(error, urllib.error.HTTPError) else 0
        print(
            json.dumps(
                {
                    "event": "model_discovery_error",
                    "tier": tier,
                    "http_status": status,
                    "error_type": type(error).__name__,
                }
            ),
            flush=True,
        )
        return 1

    if model_id_override:
        candidates = [model for model in available_models if model.get("id") == model_id_override]
    else:
        suffix = f"/{model_ref}"
        candidates = [
            model
            for model in available_models
            if str(model.get("owned_by", "")).endswith(suffix)
            or str(model.get("id", "")).endswith(suffix)
        ]
    if not candidates and len(available_models) == 1:
        candidates = available_models
    if len(candidates) != 1:
        print(
            json.dumps(
                {
                    "event": "model_discovery_error",
                    "tier": tier,
                    "error_type": "ModelSelectionError",
                    "available_model_count": len(available_models),
                }
            ),
            flush=True,
        )
        return 1

    selected_model = candidates[0]
    model_id = selected_model.get("id")
    endpoint = (selected_model.get("url") or base_url).rstrip("/") + "/v1/chat/completions"
    prompt = "Say hi and give one brief weather safety tip."
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode("utf-8")
    started_at = time.monotonic()
    deadline = started_at + duration
    counts = {"200": 0, "429": 0, "incomplete_200": 0, "other": 0}
    request_number = 0

    print(
        json.dumps(
            {
                "event": "started",
                "tier": tier,
                "model": model_id,
                "duration_seconds": duration,
                "interval_seconds": interval,
                "concurrency": concurrency,
                "max_tokens": max_tokens,
                "tls_verification": verify_tls,
            }
        ),
        flush=True,
    )

    def send_one(number):
        request_started = time.monotonic()
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        status = 0
        usage = {}
        retry_after = None
        response_complete = False
        transport_error = None
        try:
            with urllib.request.urlopen(
                request, timeout=timeout, context=request_context
            ) as response:
                status = response.status
                payload = json.loads(response.read().decode("utf-8"))
                usage = payload.get("usage") or {}
                response_complete = True
        except urllib.error.HTTPError as error:
            status = error.code
            retry_after = error.headers.get("Retry-After")
            error.close()
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            OSError,
            ValueError,
        ) as error:
            transport_error = type(error).__name__
        return {
            "event": "request",
            "tier": tier,
            "request": number,
            "http_status": status,
            "response_complete": response_complete,
            "transport_error": transport_error,
            "elapsed_ms": round((time.monotonic() - request_started) * 1000),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "retry_after": retry_after,
        }

    pending = {}
    next_submit = started_at
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        while time.monotonic() < deadline or pending:
            now = time.monotonic()
            if now < deadline and now >= next_submit and len(pending) < concurrency:
                request_number += 1
                future = pool.submit(send_one, request_number)
                pending[future] = request_number
                next_submit = now + interval
                continue

            completed, _ = wait(
                pending,
                timeout=0.2,
                return_when=FIRST_COMPLETED,
            ) if pending else (set(), set())
            for future in completed:
                pending.pop(future, None)
                result = future.result()
                if result["http_status"] == 200 and result["response_complete"]:
                    counts["200"] += 1
                elif result["http_status"] == 200:
                    counts["incomplete_200"] += 1
                elif result["http_status"] == 429:
                    counts["429"] += 1
                else:
                    counts["other"] += 1
                print(json.dumps(result), flush=True)
                if result["http_status"] in {401, 403}:
                    print(
                        json.dumps(
                            {
                                "event": "stopping",
                                "tier": tier,
                                "reason": f"HTTP {result['http_status']}",
                            }
                        ),
                        flush=True,
                    )
                    deadline = min(deadline, time.monotonic())
            if not completed and (not pending or len(pending) >= concurrency or now < next_submit):
                time.sleep(0.1)

    print(
        json.dumps(
            {
                "event": "summary",
                "tier": tier,
                "requests": request_number,
                "successes_200": counts["200"],
                "rate_limited_429": counts["429"],
                "incomplete_200": counts["incomplete_200"],
                "other_responses": counts["other"],
            }
        ),
        flush=True,
    )
    return 0 if counts["200"] + counts["429"] + counts["incomplete_200"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
