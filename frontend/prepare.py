"""Publish a frozen forecast and the shared Python kernels as static browser assets."""

import argparse
import hashlib
import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Defaults to the synthetic fixture")
    parser.add_argument("--result", type=Path, help="Completed Worker report; otherwise compute the snapshot locally")
    parser.add_argument("--name", default="Sample qualifier")
    parser.add_argument("--label", default="Synthetic demonstration · sample teams and model coefficients")
    args = parser.parse_args()
    if args.result and not args.snapshot:
        parser.error("--result requires --snapshot")
    prepared = runpy.run_path(str(REPO / "worker" / "prepare.py"))
    sys.path.insert(0, str(REPO / "worker" / "src"))
    from forecast import advance
    from snapshot import EventSnapshot

    path = args.snapshot or REPO / "worker" / "fixtures" / "forecast.json"
    snapshot = EventSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    checkpoint = None
    if args.result:
        report = json.loads(args.result.read_text(encoding="utf-8"))
        if report.get("status") != "complete" or not report.get("result"):
            parser.error("--result must be a completed Worker report")
        if set(report["result"]["teams"]) != {str(team) for team in snapshot.field.predicted}:
            parser.error("result teams must match snapshot teams")
    else:
        while True:
            checkpoint, report = advance(snapshot, checkpoint)
            if report["status"] != "running":
                break
        if report["status"] != "complete":
            parser.error("snapshot exhausted its iteration budget without a publishable result")
    # The browser owns a frozen copy, independent of the source D1 revision.
    snapshot.season_prior = None
    output = ROOT / "public" / "generated"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "engine.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for package in ("sim", "warehouse"):
            for name in ("__init__.py", *prepared["MODULES"][package]):
                source = REPO / package / "src" / package / name
                bundle.writestr(f"{package}/{name}", source.read_bytes())
        for name in ("snapshot.py", "forecast.py"):
            bundle.writestr(name, (REPO / "worker" / "src" / name).read_bytes())
    engine_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    document = {
        "name": args.name,
        "label": args.label,
        "published_at": datetime.now(UTC).isoformat(),
        "engine_url": f"/generated/engine.zip?v={engine_hash}",
        "engine_sha256": engine_hash,
        "snapshot": snapshot.model_dump(mode="json"),
        "forecast": report["result"],
    }
    (output / "event.json").write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
    print(f"Published {args.name}: {len(snapshot.field.predicted)} teams, {report['result']['iterations']} iterations")


if __name__ == "__main__":
    main()
