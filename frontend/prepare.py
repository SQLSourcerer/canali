"""Prepare a static demo, or package a frozen forecast for the event browser."""

import argparse
import hashlib
import io
import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from tarfile import TarFile, TarInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUTPUT = ROOT / "public" / "generated"


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")


def build_engine(output=OUTPUT):
    prepared = runpy.run_path(str(REPO / "worker" / "prepare.py"))
    sys.path.insert(0, str(REPO / "worker" / "src"))
    buffer = io.BytesIO()
    with TarFile(fileobj=buffer, mode="w") as bundle:
        for package in ("sim", "warehouse"):
            for name in ("__init__.py", *prepared["MODULES"][package]):
                source = REPO / package / "src" / package / name
                data = source.read_bytes()
                member = TarInfo(f"{package}/{name}")
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        for name in ("snapshot.py", "forecast.py"):
            data = (REPO / "worker" / "src" / name).read_bytes()
            member = TarInfo(name)
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
        for name in ("partner_comparison.py", "auto_leave.py"):
            data = (ROOT / name).read_bytes()
            member = TarInfo(name)
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    filename = f"engine-{digest}.tar"
    (output / filename).write_bytes(buffer.getvalue())
    return {
        "engine_url": f"/generated/{filename}",
        "engine_sha256": digest,
        "engine_version": runpy.run_path(str(REPO / "worker" / "src" / "engine_version.py"))["ENGINE_VERSION"],
    }


def publish_event(metadata, snapshot, forecast, engine, *, revision=None, output=OUTPUT):
    if set(forecast["teams"]) != {str(team) for team in snapshot.field.predicted}:
        raise ValueError("result teams must match snapshot teams")
    source_hash = hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
    frozen = snapshot.model_copy(update={"season_prior": None})
    document = {
        **metadata,
        **engine,
        "published_at": datetime.now(UTC).isoformat(),
        "source_revision": revision,
        "source_snapshot_sha256": source_hash,
        "snapshot": frozen.model_dump(mode="json"),
        "forecast": forecast,
    }
    data = json.dumps(document, allow_nan=False).encode()
    filename = f"event-{hashlib.sha256(data).hexdigest()}.json"
    (output / filename).write_bytes(data)
    return {
        **metadata,
        "forecast_url": f"/generated/{filename}",
        "status": "complete",
        "published_at": document["published_at"],
        "source_revision": revision,
        "played": sum(frozen.progress.played) if frozen.progress else 0,
        "scheduled": len(frozen.schedule.stations) if frozen.schedule else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Defaults to the synthetic fixture")
    parser.add_argument("--result", type=Path, help="Completed Worker report; otherwise compute locally")
    parser.add_argument("--name", default="Sample qualifier")
    parser.add_argument("--label", default="Synthetic demonstration · sample teams and model coefficients")
    args = parser.parse_args()
    if args.result and not args.snapshot:
        parser.error("--result requires --snapshot")
    engine = build_engine()
    from forecast import advance
    from snapshot import EventSnapshot

    path = args.snapshot or REPO / "worker" / "fixtures" / "forecast.json"
    snapshot = EventSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    if args.result:
        report = json.loads(args.result.read_text(encoding="utf-8"))
    else:
        checkpoint = None
        while True:
            checkpoint, report = advance(snapshot, checkpoint)
            if report["status"] != "running":
                break
    if report.get("status") != "complete" or not report.get("result"):
        parser.error("a completed forecast is required for publication")
    metadata = {
        "code": "DEMO",
        "season": snapshot.rule_pack.season,
        "name": args.name,
        "label": args.label,
        "date_start": None,
        "date_end": None,
        "city": "",
        "venue": "",
        "type": "Demonstration",
        "source_url": None,
        "teams": {str(team): f"Team {team}" for team in snapshot.field.predicted},
    }
    event = publish_event(metadata, snapshot, report["result"], engine)
    write_json(
        OUTPUT / "catalog.json",
        {
            "season": snapshot.rule_pack.season,
            "region": "USPA",
            "region_name": "Pennsylvania",
            "published_at": datetime.now(UTC).isoformat(),
            "events": [event],
        },
    )
    print(f"Published {args.name}: {len(snapshot.field.predicted)} teams, {report['result']['iterations']} iterations")


if __name__ == "__main__":
    main()
