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
    check_forecast()
    print("Local Worker/D1 smoke test passed: ratings, forecasts, reruns, corrections and input validation.")


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
