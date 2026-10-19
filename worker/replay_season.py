"""Import a selected FIRST season corpus and resume bounded local D1 replay steps."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from warehouse.ingest.client import FtcEventsClient


def checked(response):
    if response.status_code not in (200, 202):
        raise SystemExit(f"Local Worker HTTP {response.status_code}: {response.text}")
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", type=int)
    parser.add_argument("--events", required=True, help="Comma-separated event codes, including divisions as needed")
    parser.add_argument("--config", type=Path, help="Optional previous_norm and second_norm mappings")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    url = urlparse(args.base_url)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.path not in ("", "/"):
        parser.error("--base-url must be a local HTTP Worker URL")
    if not 2015 <= args.season <= 2100:
        parser.error("invalid season")
    requested = set(args.events.split(","))
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    archive = Path(__file__).resolve().parents[1] / "var" / "worker-season" / str(args.season)
    archive.mkdir(parents=True, exist_ok=True)
    with FtcEventsClient() as client, httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120) as worker:
        events = {event["code"]: event for event in client.season_events(args.season).data["events"]}
        if requested - events.keys():
            parser.error(f"Unknown FIRST event codes: {sorted(requested - events.keys())}")
        checked(worker.put(f"/seasons/{args.season}", json=config))
        for code in sorted(requested):
            teams = client.event_teams(args.season, code)
            schedule = client.hybrid_schedule(args.season, code, "qual")
            if teams.status != 200 or schedule.status != 200:
                raise SystemExit(f"FIRST HTTP {teams.status}/{schedule.status} for {code}; replay not started")
            source = {"event": events[code], "teams": teams.data, "schedule": schedule.data}
            report = checked(worker.put(f"/seasons/{args.season}/events/{code}", json=source))
            (archive / f"{code}.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
            print(json.dumps(report))
        while True:
            response = worker.post(f"/seasons/{args.season}/step")
            report = checked(response)
            print(json.dumps(report))
            if report["status"] == "complete":
                break


if __name__ == "__main__":
    main()
