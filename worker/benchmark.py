"""Benchmark a frozen forecast on a local or authenticated hosted Worker."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def benchmark(client, snapshot, event, max_steps, report):
    """Keep a record even when a request fails; never retry charged work automatically."""

    def request(method, path, **kwargs):
        start = perf_counter()
        response = client.request(method, path, **kwargs)
        report["requests"].append(
            {
                "method": method,
                "path": path,
                "status": response.status_code,
                "elapsed_ms": (perf_counter() - start) * 1000,
                "cf_ray": response.headers.get("cf-ray"),
            }
        )
        response.raise_for_status()
        return response.json()

    report["health"] = request("GET", "/health")
    report["input"] = request("PUT", f"/forecasts/{event}", json=snapshot)
    previous = -1
    for _ in range(max_steps):
        state = request("POST", f"/forecasts/{event}/step")
        report["progress"].append({k: v for k, v in state.items() if k != "result"})
        if state["iterations"] <= previous and state["status"] == "running":
            raise RuntimeError("forecast made no progress")
        previous = state["iterations"]
        if state["status"] != "running":
            report["forecast"] = state
            return
    raise RuntimeError("request budget reached; rerun with the same --event to resume")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--event", default=f"bench-{uuid4().hex}", help="Reuse this key to resume, or omit for a fresh run"
    )
    parser.add_argument("--max-steps", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("../var/worker-benchmark/report.json"))
    args = parser.parse_args()
    url = urlparse(args.base_url)
    local = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
    remote = url.scheme == "https" and (url.hostname or "").endswith(".workers.dev")
    if not (local or remote) or url.path not in ("", "/") or url.username or url.password or url.query or url.fragment:
        parser.error("use a loopback HTTP URL or HTTPS workers.dev URL, without credentials, path or query")
    if not 1 <= args.max_steps <= 1000:
        parser.error("--max-steps must be between 1 and 1000")
    if (
        not args.event.isascii()
        or not 1 <= len(args.event) <= 64
        or not args.event.replace("-", "").replace("_", "").isalnum()
    ):
        parser.error("--event must use 1 to 64 ASCII letters, digits, underscores or hyphens")
    token = os.environ.get("CANALI_BENCHMARK_TOKEN", "")
    if remote and len(token) < 32:
        parser.error("set CANALI_BENCHMARK_TOKEN to the deployed secret (at least 32 characters)")
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    # Frozen benchmark inputs do not depend on the local database's season revisions.
    snapshot["season_prior"] = None
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "event": args.event,
        "snapshot_sha256": hashlib.sha256(json.dumps(snapshot).encode()).hexdigest(),
        "requests": [],
        "progress": [],
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(
            base_url=args.base_url.rstrip("/"), headers=headers, timeout=120, follow_redirects=False
        ) as client:
            benchmark(client, snapshot, args.event, args.max_steps, report)
    except (httpx.HTTPError, RuntimeError) as exc:
        report["error"] = str(exc)
        raise SystemExit(f"Benchmark stopped: {exc}. Report: {args.output}") from exc
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{args.event}: {report['forecast']['iterations']} iterations; report: {args.output}")


if __name__ == "__main__":
    main()
