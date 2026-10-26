"""Continuous concurrent SSE load through MaaS; logs metrics, never tokens or text."""

import collections
import json
import os
import random
import signal
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid


BASE_URL = os.environ["MAAS_BASE_URL"].rstrip("/")
MODEL = os.environ.get("MAAS_MODEL", "gpt-oss-20b")
SUBSCRIPTION = os.environ.get("MAAS_SUBSCRIPTION", "gpt-oss-20b-stress")
TOKEN_FILE = os.environ.get("TOKEN_FILE", "/var/run/maas/token")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "256"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))
PROMPT_RECORDS = int(os.environ.get("PROMPT_RECORDS", "64"))
TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "600"))
REPORT_INTERVAL = int(os.environ.get("REPORT_INTERVAL_SECONDS", "30"))
STARTUP_INTERVAL = float(os.environ.get("STARTUP_INTERVAL_SECONDS", "0.2"))
if not 1 <= CONCURRENCY <= 512:
    raise ValueError("CONCURRENCY must be between 1 and 512")
if min(MAX_TOKENS, PROMPT_RECORDS, TIMEOUT, REPORT_INTERVAL) < 1:
    raise ValueError("Output size, prompt size, timeout and report interval must be positive")
if not 0 <= STARTUP_INTERVAL <= 10:
    raise ValueError("STARTUP_INTERVAL_SECONDS must be between 0 and 10")

TLS = ssl.create_default_context()
if os.environ.get("CA_BUNDLE"):
    TLS.load_verify_locations(os.environ["CA_BUNDLE"])
STOP = threading.Event()
LOCK = threading.Lock()
COUNTS = collections.Counter()
ERRORS = collections.Counter()
LAST_ERROR_LOG = {}
TTFT = []
LATENCY = []
STARTED = time.monotonic()


def emit(event, **values):
    print(json.dumps({"event": event, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **values}), flush=True)


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int((len(values) - 1) * fraction))], 3)


def make_payload():
    # Unique data at the beginning prevents repeated identical prompt prefixes.
    nonce = uuid.uuid4().hex
    records = "\n".join(
        f"record {i}: region={random.randrange(20)} arrivals={random.randrange(100, 9000)} "
        f"latency_ms={random.randrange(10, 5000)} failures={random.randrange(40)}"
        for i in range(PROMPT_RECORDS)
    )
    prompt = (
        f"Independent simulation {nonce}. Analyze this synthetic service dataset.\n{records}\n"
        "Write a detailed engineering assessment with calculations, comparisons, capacity planning, "
        "bottleneck analysis, tradeoffs, and an ordered remediation plan. Continue in depth."
    )
    return json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.8,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode()


def worker(worker_id):
    while not STOP.is_set():
        start = time.monotonic()
        first_token = None
        usage = {}
        failure = None
        with LOCK:
            COUNTS["started"] += 1
            COUNTS["inflight"] += 1
        try:
            # Read on every request so kubelet token rotation is picked up automatically.
            with open(TOKEN_FILE, encoding="utf-8") as handle:
                token = handle.read().strip()
            request = urllib.request.Request(
                BASE_URL + "/llm/" + MODEL + "/v1/chat/completions",
                data=make_payload(),
                headers={
                    "Authorization": "Bearer " + token,
                    "X-MaaS-Subscription": SUBSCRIPTION,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            )
            with urllib.request.urlopen(request, context=TLS, timeout=TIMEOUT) as response:
                for line in response:
                    if not line.startswith(b"data:"):
                        continue
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("error"):
                        raise RuntimeError("stream_error")
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if first_token is None and any(delta.get(field) for field in ("content", "reasoning", "reasoning_content")):
                            first_token = time.monotonic() - start
                            with LOCK:
                                TTFT.append(first_token)
            if first_token is None:
                raise RuntimeError("empty_stream")
            with LOCK:
                COUNTS["succeeded"] += 1
                COUNTS["prompt_tokens"] += usage.get("prompt_tokens", 0)
                COUNTS["completion_tokens"] += usage.get("completion_tokens", 0)
                if not usage:
                    COUNTS["missing_usage"] += 1
                LATENCY.append(time.monotonic() - start)
        except urllib.error.HTTPError as error:
            failure = "http_" + str(error.code)
            error.close()
        except Exception as error:
            # Do not log request headers, credentials, payloads, or generated text.
            failure = type(error).__name__
        finally:
            with LOCK:
                COUNTS["inflight"] -= 1
                if failure:
                    COUNTS["failed"] += 1
                    ERRORS[failure] += 1
        if failure:
            now = time.monotonic()
            with LOCK:
                should_log = now - LAST_ERROR_LOG.get(failure, 0) >= REPORT_INTERVAL
                if should_log:
                    LAST_ERROR_LOG[failure] = now
            if should_log:
                emit("request_error", worker=worker_id, error=failure)
            delay = 30 if failure in ("http_401", "http_403") else random.uniform(2, 5)
            STOP.wait(delay)


def main():
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: STOP.set())
    emit("started", model=MODEL, concurrency=CONCURRENCY, max_tokens=MAX_TOKENS,
         prompt_records=PROMPT_RECORDS, subscription=SUBSCRIPTION, continuous=True,
         startup_interval_seconds=STARTUP_INTERVAL)
    threads = []
    for worker_id in range(CONCURRENCY):
        thread = threading.Thread(target=worker, args=(worker_id,), daemon=True)
        thread.start()
        threads.append(thread)
        if STOP.wait(STARTUP_INTERVAL):
            break
    previous = collections.Counter()
    previous_time = STARTED
    while not STOP.wait(REPORT_INTERVAL):
        now = time.monotonic()
        with LOCK:
            current = COUNTS.copy()
            errors = ERRORS.copy()
            ttft, latency = TTFT[:], LATENCY[:]
            TTFT.clear()
            LATENCY.clear()
        interval = now - previous_time
        emit("summary", uptime_seconds=round(now - STARTED), inflight=current["inflight"],
             requests_started=current["started"], succeeded=current["succeeded"], failed=current["failed"],
             requests_per_second=round((current["succeeded"] - previous["succeeded"]) / interval, 3),
             completion_tokens_per_second=round((current["completion_tokens"] - previous["completion_tokens"]) / interval, 1),
             prompt_tokens_per_second=round((current["prompt_tokens"] - previous["prompt_tokens"]) / interval, 1),
             total_completion_tokens=current["completion_tokens"], errors=dict(errors),
             ttft_p50_seconds=percentile(ttft, 0.5), ttft_p95_seconds=percentile(ttft, 0.95),
             latency_p95_seconds=percentile(latency, 0.95), missing_usage=current["missing_usage"])
        previous, previous_time = current, now
    emit("stopping")
    deadline = time.monotonic() + 5
    for thread in threads:
        thread.join(timeout=max(0, deadline - time.monotonic()))


if __name__ == "__main__":
    main()
