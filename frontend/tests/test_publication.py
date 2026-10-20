import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare import build_engine
from publish import export_catalog
from snapshot import EventSnapshot

ROOT = Path(__file__).parents[2]


def test_publication_keeps_matching_revisions_rosters_and_content_addressed_assets(tmp_path):
    engine = build_engine(tmp_path)
    assert build_engine(tmp_path) == engine
    decoded = (tmp_path / Path(engine["engine_url"]).name).read_bytes()
    assert hashlib.sha256(decoded).hexdigest() == engine["engine_sha256"]
    with tarfile.open(fileobj=io.BytesIO(decoded)) as archive:
        for member in archive.getmembers():
            assert member.isfile() and not member.name.startswith("/") and ".." not in Path(member.name).parts
            source = (
                ROOT
                / ("frontend" if member.name in ("partner_comparison.py", "auto_leave.py") else "worker/src")
                / member.name
            )
            assert archive.extractfile(member).read() == source.read_bytes()
    snap = EventSnapshot.model_validate_json((ROOT / "worker/fixtures/forecast.json").read_text())
    event = {
        "code": "A",
        "regionCode": "USPA",
        "name": "Test qualifier",
        "type": "2",
        "dateStart": "2026-01-10T00:00:00",
        "dateEnd": "2026-01-10T00:00:00",
    }
    teams = [{"teamNumber": t, "nameShort": f"Name {t}"} for t in snap.field.predicted]
    first = SimpleNamespace(event_teams=lambda *_: SimpleNamespace(status=200, data={"teams": teams}))
    packet = {
        "event": "2025-A",
        "revision": 7,
        "engine_version": engine["engine_version"],
        "status": "complete",
        "snapshot": snap.model_dump(mode="json"),
        "forecast": {"iterations": 1000, "teams": {str(t): {} for t in snap.field.predicted}},
    }

    def serve(request):
        return httpx.Response(200 if request.url.path.endswith("2025-A/export") else 404, json=packet)

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(serve)) as worker:

        def publish(events):
            return export_catalog(
                events,
                2025,
                region="USPA",
                label="Historical demo",
                first=first,
                worker=worker,
                engine=engine,
                output=tmp_path,
            )

        catalog = publish([event, {**event, "code": "B"}, {**event, "code": "BR", "regionCode": "BR"}])
        assert len(catalog["events"]) == 2
        assert catalog["events"][1]["forecast_url"] is None
        doc = json.loads((tmp_path / Path(catalog["events"][0]["forecast_url"]).name).read_text())
        assert doc["source_revision"] == 7 and doc["teams"]["1"] == "Name 1"
        assert doc["snapshot"]["season_prior"] is None
        before = (tmp_path / "catalog.json").read_bytes()
        packet["engine_version"] = "obsolete"
        with pytest.raises(ValueError, match="engine differs"):
            publish([event])
        assert (tmp_path / "catalog.json").read_bytes() == before
        packet["engine_version"] = engine["engine_version"]
        teams.pop()
        with pytest.raises(ValueError, match="roster differs"):
            publish([event])
        assert (tmp_path / "catalog.json").read_bytes() == before
        with pytest.raises(ValueError, match="no matching"):
            publish([])
