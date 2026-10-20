"""Export a region's FIRST catalog and matching D1 forecasts into static assets."""

import argparse
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from prepare import OUTPUT, build_engine, publish_event, write_json

EVENT_TYPES = {"0": "Scrimmage", "2": "Qualifier", "4": "Championship", "10": "Off-season"}


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
        catalog.append(
            publish_event(
                {**metadata, "teams": names},
                snapshot,
                packet["forecast"],
                engine,
                revision=packet["revision"],
                output=output,
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
    write_json(output / "catalog.json", document)
    return document


def main():
    from warehouse.ingest.client import FtcEventsClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", type=int)
    parser.add_argument("--region", default="USPA")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--label", required=True, help="Data quality, model and historical replay assumptions")
    args = parser.parse_args()
    url = urlparse(args.base_url)
    local = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
    remote = url.scheme == "https" and url.hostname == "canali-benchmark.mjhanson.workers.dev"
    if not (local or remote) or url.path not in ("", "/") or url.username or url.password or url.query or url.fragment:
        parser.error("use a loopback URL or the project's HTTPS benchmark Worker")
    if not 2015 <= args.season <= 2100 or not args.region.isascii() or not args.region.isalnum():
        parser.error("invalid season or region")
    token = os.environ.get("CANALI_BENCHMARK_TOKEN", "")
    if remote and len(token) < 32:
        parser.error("set CANALI_BENCHMARK_TOKEN for authenticated remote export")
    engine = build_engine()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with (
        FtcEventsClient() as first,
        httpx.Client(
            base_url=args.base_url.rstrip("/"), headers=headers, timeout=120, follow_redirects=False
        ) as worker,
    ):
        events = first.season_events(args.season)
        if events.status != 200:
            parser.error("FIRST event catalog unavailable")
        catalog = export_catalog(
            events.data["events"],
            args.season,
            region=args.region,
            label=args.label,
            first=first,
            worker=worker,
            engine=engine,
        )
    complete = sum(e["status"] == "complete" for e in catalog["events"])
    print(f"Published {len(catalog['events'])} event listings, {complete} completed forecasts")


if __name__ == "__main__":
    main()
