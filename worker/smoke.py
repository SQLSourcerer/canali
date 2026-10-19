"""Exercise a running local Python Worker and real local D1 binding."""

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8787"


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
    print("Local Worker/D1 smoke test passed: ratings, forecasts, reruns, corrections and input validation.")


if __name__ == "__main__":
    main()
