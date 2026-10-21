"""Export a region's FIRST catalog and matching D1 forecasts into static assets."""

import argparse
import json
import re
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import httpx
from prepare import OUTPUT, build_engine, publish_event, write_json
from static_publish import STATE, deploy_if_changed, prepare_site, publication_lock

sys.path.append(str(Path(__file__).resolve().parents[1] / "worker"))
from remote_access import request_headers

EVENT_TYPES = {"0": "Scrimmage", "2": "Qualifier", "4": "Championship", "10": "Off-season"}


def previous_snapshot(output, url):
    if not url or re.fullmatch(r"/generated/event-[0-9a-f]{64}\.json", url) is None:
        return None
    path = output / Path(url).name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def metadata_for(event, season, label):
    return {
        "code": event["code"],
        "season": season,
        "name": event["name"].strip(),
        "date_start": event["dateStart"].split("T")[0],
        "date_end": (event.get("dateEnd") or event["dateStart"]).split("T")[0],
        "city": (event.get("city") or "").strip(),
        "venue": (event.get("venue") or "").strip(),
        "type": EVENT_TYPES[str(event["type"])],
        "label": label,
        "source_url": f"https://ftc-events.firstinspires.org/{season}/{event['code']}",
    }


def export_catalog(events, season, *, region, label, first, worker, engine, output=OUTPUT):
    from snapshot import EventSnapshot

    catalog_path = output / "catalog.json"
    previous = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else None
    previous_events = {(row["season"], row["code"]): row for row in previous["events"]} if previous else {}
    catalog = []
    for event in sorted(events, key=lambda e: (e["dateStart"], e["code"])):
        if event.get("regionCode") != region or str(event["type"]) not in EVENT_TYPES:
            continue
        metadata = metadata_for(event, season, label)
        response = worker.get(f"/forecasts/{season}-{event['code']}/export")
        if response.status_code == 404:
            catalog.append({**metadata, "status": "unpublished", "forecast_url": None})
            continue
        response.raise_for_status()
        packet = response.json()
        if packet["event"] != f"{season}-{event['code']}":
            raise ValueError("export event differs from catalog")
        if packet["engine_version"] != engine["engine_version"]:
            raise ValueError("deployed engine differs from local sources; deploy matching sources before publication")
        if packet["status"] != "complete":
            catalog.append({**metadata, "status": packet["status"], "forecast_url": None})
            continue
        snapshot = EventSnapshot.model_validate(packet["snapshot"])
        if snapshot.rule_pack.season != season:
            raise ValueError("forecast season differs from catalog")
        roster = first.event_teams(season, event["code"])
        if roster.status != 200:
            raise ValueError(f"FIRST roster unavailable for {event['code']}")
        names = {
            str(t["teamNumber"]): t.get("nameShort") or t.get("nameFull") or f"Team {t['teamNumber']}"
            for t in roster.data["teams"]
        }
        if set(names) != {str(t) for t in snapshot.field.predicted}:
            raise ValueError(f"FIRST roster differs from forecast for {event['code']}")
        old = previous_events.get((season, event["code"]), {}).get("forecast_url")
        previous_document = previous_snapshot(output, old)
        catalog.append(
            publish_event(
                {**metadata, "teams": names},
                snapshot,
                packet["forecast"],
                engine,
                revision=packet["revision"],
                output=output,
                previous=previous_document,
                computed_at=packet.get("computed_at"),
            )
        )
    if not catalog:
        raise ValueError("no matching competition events; existing catalog was not replaced")
    document = {
        "season": season,
        "region": region,
        "region_name": "Pennsylvania" if region == "USPA" else region,
        "published_at": datetime.now(UTC).isoformat(),
        "events": catalog,
    }
    if previous and {k: v for k, v in previous.items() if k != "published_at"} == {
        k: v for k, v in document.items() if k != "published_at"
    }:
        document["published_at"] = previous["published_at"]
    write_json(output / "catalog.json", document)
    return document


def run_publisher(args):
    from warehouse.ingest.client import FtcEventsClient

    headers = request_headers(args.base_url)
    with publication_lock(STATE / "publisher.lock"):
        output = prepare_site(Path(__file__).parent / "dist", STATE / "site") if args.deploy else OUTPUT
        engine = build_engine(output)
        with (
            FtcEventsClient() as first,
            httpx.Client(
                base_url=args.base_url.rstrip("/"), headers=headers, timeout=120, follow_redirects=False
            ) as worker,
        ):
            while True:
                try:
                    events = first.season_events(args.season)
                    if events.status != 200:
                        raise ValueError("FIRST event catalog unavailable")
                    catalog = export_catalog(
                        events.data["events"],
                        args.season,
                        region=args.region,
                        label=args.label,
                        first=first,
                        worker=worker,
                        engine=engine,
                        output=output,
                    )
                    if args.deploy:
                        changed = deploy_if_changed(STATE / "site", STATE / "deployed.json")
                        print("Static publication deployed" if changed else "Static publication unchanged", flush=True)
                    else:
                        print(f"Exported {len(catalog['events'])} event listings", flush=True)
                except (httpx.HTTPError, ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                    if not args.watch:
                        raise
                    print(f"Publication failed; retrying after {args.interval_s}s: {exc}", file=sys.stderr, flush=True)
                if not args.watch:
                    return
                time.sleep(args.interval_s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", type=int)
    parser.add_argument("--region", default="USPA")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--label", required=True, help="Data quality, model and historical replay assumptions")
    parser.add_argument(
        "--deploy", action="store_true", help="Deploy changed static assets using the existing dist build"
    )
    parser.add_argument("--watch", action="store_true", help="Keep exporting and retry failed publication cycles")
    parser.add_argument("--interval-s", type=int, default=60, help="Seconds between completed publication cycles")
    args = parser.parse_args()
    try:
        request_headers(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    if not 2015 <= args.season <= 2100 or not args.region.isascii() or not args.region.isalnum():
        parser.error("invalid season or region")
    if args.interval_s < 1:
        parser.error("--interval-s must be positive")
    with suppress(KeyboardInterrupt):
        run_publisher(args)


if __name__ == "__main__":
    main()
