"""Exercise a running local Python Worker and real local D1 binding."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8787"
sys.path.insert(0, str(Path(__file__).parent / "src"))


def request(path, method="GET", document=None):
    body = None if document is None else json.dumps(document).encode()
    req = Request(BASE + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def main():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "event.json").read_text())
    assert request("/health")[0] == 200
    status, uploaded = request("/events/SYNTH", "PUT", fixture)
    assert status == 200, uploaded
    revision = uploaded["revision"]
    assert request("/events/SYNTH")[0] == 404
    status, first = request("/events/SYNTH/run", "POST")
    assert status == 200, first
    assert first["revision"] == revision
    assert [team["epa"] for team in first["result"]["teams"]] == [57, 57, 43, 43]
    assert request("/events/SYNTH")[1] == first
    assert request("/events/SYNTH/run", "POST")[1] == first
    fixture["matches"][0]["red_score"] = 100
    assert request("/events/SYNTH", "PUT", fixture)[1]["revision"] == revision + 1
    assert request("/events/SYNTH")[0] == 404
    status, corrected = request("/events/SYNTH/run", "POST")
    assert status == 200, corrected
    assert corrected["result"]["teams"][0]["epa"] == 50
    fixture["matches"][0]["red"] = [1, 1]
    assert request("/events/SYNTH", "PUT", fixture)[0] == 400
    assert request("/events/SYNTH")[1] == corrected
    check_import()
    check_season()
    check_forecast()
    print("Local Worker/D1 smoke test passed: ratings, forecasts, reruns, corrections and input validation.")


def fixture_source():
    document = json.loads((Path(__file__).parent / "fixtures" / "event.json").read_text())
    schedule = []
    for match in document.pop("matches"):
        schedule.append(
            {
                "matchNumber": match["ordinal"],
                "tournamentLevel": "QUALIFICATION",
                "teams": [
                    {"teamNumber": team, "station": f"{side.title()}{index}"}
                    for side in ("red", "blue")
                    for index, team in enumerate(match[side], 1)
                ],
                "scoreRedFinal": match["red_score"],
                "scoreRedFoul": 0,
                "scoreBlueFinal": match["blue_score"],
                "scoreBlueFoul": 0,
            }
        )
    return {
        "season": 2025,
        "event_code": "IMPORT",
        "parameters": document,
        "teams": {"teams": [{"teamNumber": t["number"]} for t in document["teams"]]},
        "schedule": {"schedule": schedule},
    }


def check_import():
    source = fixture_source()
    document = source["parameters"]
    path = "/imports/2025-IMPORT"
    status, uploaded = request(path, "PUT", source)
    assert status == 200, uploaded
    revision = uploaded["revision"]
    assert request(path)[1]["source"] == source
    result_path = "/events/2025-IMPORT"
    status, report = request(result_path + "/run", "POST")
    assert status == 200, report
    assert [t["epa"] for t in report["result"]["teams"]] == [57, 57, 43, 43]
    assert request(path, "PUT", source)[1]["revision"] == revision
    assert request(result_path)[1] == report
    source["schedule"]["schedule"][0]["scoreRedFinal"] += 10
    assert request(path, "PUT", source)[1]["revision"] == revision + 1
    assert request(result_path)[0] == 404
    source["schedule"]["schedule"][0]["scoreRedFoul"] = None
    assert request(path, "PUT", source)[0] == 400
    assert request(path)[1]["revision"] == revision + 1
    # A direct prepared-input replacement must not retain the old source attribution.
    document["matches"] = json.loads((Path(__file__).parent / "fixtures" / "event.json").read_text())["matches"]
    assert request(result_path, "PUT", document)[0] == 200
    assert request(path)[0] == 404


def check_season():
    import uuid

    import numpy as np
    from season import prepare

    from epa.constants import for_season
    from epa.replay import TAG_POST_EVENT, TAG_PRE_EVENT, replay_season
    from epa.scale import Scale
    from warehouse.rules.partition import ResolvedPartition

    year = 2099
    path = f"/seasons/{year}"
    # Changing configuration resets this synthetic corpus on repeated smoke runs.
    assert request(path, "PUT", {"previous_norm": {"1": 1550}})[0] == 200
    assert request(path, "PUT", {})[0] == 200
    sources = []
    for index, code in enumerate(("SEASON_A", "SEASON_B", "SEASON_C"), 1):
        source = fixture_source()
        source = {
            "teams": source["teams"],
            "schedule": source["schedule"],
            "event": {
                "code": code,
                "eventId": str(uuid.UUID(int=index)),
                "dateStart": f"{year}-{index:02d}-01",
                "typeName": "League Meet",
            },
        }
        sources.append(source)
        status, report = request(path + "/events/" + code, "PUT", source)
        assert status == 200, report
    assert request(path + "/priors/SEASON_B")[0] == 409

    def finish(codes):
        for code in codes:
            status, report = request(path + "/step", "POST")
            assert status == 202 and report["event"] == code, report
        assert request(path + "/step", "POST")[1]["status"] == "complete"

    def compare():
        events = [prepare(source, source["event"]["code"]) for source in sources]
        result = replay_season(
            [match for event in events for match in event.stream(year)],
            constants=for_season(year),
            partition=ResolvedPartition.total_only(year),
            season_scale=None,
            init_scale=Scale(**request(path)[1]["init_scale"]),
            layoff_boost=for_season(year).layoff_boost,
            compute_norm=False,
        )
        for event in events:
            status, report = request(path + "/priors/" + event.code)
            assert status == 200, report
            expected = {
                row.team_number: row.epa_scaled
                for row in result.rows
                if row.tag == TAG_PRE_EVENT and row.event_id == event.event_id
            }
            np.testing.assert_allclose(
                [t["epa"] for t in report["teams"]],
                [expected[t["number"]] for t in report["teams"]],
                rtol=1e-12,
                atol=1e-12,
            )
        return events, result

    finish(["SEASON_A", "SEASON_B", "SEASON_C"])
    events, native = compare()
    parameters = fixture_source()["parameters"]
    parameters.update(request(path + "/priors/SEASON_C")[1])
    parameters["matches"] = [match.model_dump() for match in events[-1].matches]
    result_path = "/events/2099-SEASON_C"
    assert request(result_path, "PUT", parameters)[0] == 200
    status, report = request(result_path + "/run", "POST")
    assert status == 200, report
    expected = {
        row.team_number: row.epa_scaled
        for row in native.rows
        if row.tag == TAG_POST_EVENT and row.event_id == events[-1].event_id
    }
    np.testing.assert_allclose(
        [t["epa"] for t in report["result"]["teams"]],
        [expected[t["number"]] for t in report["result"]["teams"]],
        rtol=1e-12,
        atol=1e-12,
    )
    sources[1]["schedule"]["schedule"][0]["scoreRedFinal"] += 20
    assert request(path + "/events/SEASON_B", "PUT", sources[1])[0] == 200
    assert request(path)[1]["cursor"].endswith(":SEASON_A")
    assert request(result_path)[0] == 404
    assert request(result_path + "/run", "POST")[0] == 404
    finish(["SEASON_B", "SEASON_C"])
    compare()
    assert request(result_path)[0] == 404
    print("Season replay passed: native priors, event totals, correction replay and stale-result invalidation.")


def check_forecast():
    import numpy as np
    from snapshot import EventSnapshot

    from sim.runner import run_event

    document = json.loads((Path(__file__).parent / "fixtures" / "forecast.json").read_text())
    path = "/forecasts/SYNTH"
    status, uploaded = request(path, "PUT", document)
    assert status == 200, uploaded
    revision = uploaded["revision"]
    assert request(path)[0] == 404
    status, report = request(path + "/step", "POST")
    assert status == 202, report
    assert 0 < report["iterations"] <= 32
    assert report["result"] is None
    assert request(path)[1] == report
    # Each request resumes only from counts and the RNG state saved in D1.
    for _ in range(document["max_iterations"]):
        before = report["iterations"]
        status, report = request(path + "/step", "POST")
        assert status in (200, 202), report
        assert report["revision"] == revision
        assert before < report["iterations"] <= before + 32
        if report["status"] != "running":
            break
    assert report["status"] == "complete", report
    assert request(path)[1] == report
    assert request(path + "/step", "POST")[1] == report
    snapshot = EventSnapshot.model_validate(document)
    native = run_event(
        snapshot.draw(),
        snapshot.rule_pack,
        snapshot.models.build(),
        np.random.default_rng(snapshot.seed),
        slots=snapshot.slots,
        progress=snapshot.progress.build(),
        tolerance=snapshot.tolerance,
        min_iterations=snapshot.min_iterations,
    )
    assert report["result"] == json.loads(json.dumps(asdict(native)))
    document["progress"]["score"][0][0] += 20
    assert request(path, "PUT", document)[1]["revision"] == revision + 1
    assert request(path)[0] == 404
    status, restarted = request(path + "/step", "POST")
    assert status == 202, restarted
    assert 0 < restarted["iterations"] <= 32
    document["models"]["rp_curves"] = {}
    assert request(path, "PUT", document)[0] == 400
    assert request(path)[1] == restarted
    print("Full event forecast passed: native parity, D1 resume, convergence and correction invalidation.")


if __name__ == "__main__":
    main()
