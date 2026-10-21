"""Static publication retries failed deploys without coupling visitor traffic to the backend."""

import json
import subprocess
import sys
import tomllib
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from static_publish import deploy_if_changed, prepare_site, publication_lock


def test_deployment_skips_unchanged_data_and_retries_without_losing_last_success(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("compiled app")
    state = tmp_path / "deployed.json"
    calls = []

    def deploy(command, **kwargs):
        calls.append(command)
        assert kwargs["check"]
        assert "--assets" in command

    assert deploy_if_changed(site, state, run=deploy)
    assert not deploy_if_changed(site, state, run=deploy)
    assert len(calls) == 1
    previous = state.read_bytes()
    (site / "catalog.json").write_text('{"revision":2}')

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "wrangler")

    with pytest.raises(subprocess.CalledProcessError):
        deploy_if_changed(site, state, run=fail)
    assert state.read_bytes() == previous
    assert deploy_if_changed(site, state, run=deploy)
    assert not deploy_if_changed(site, state, run=deploy)
    assert len(calls) == 2


def test_restart_retains_published_snapshots_but_refreshes_compiled_client(tmp_path):
    dist, site = tmp_path / "dist", tmp_path / "site"
    (dist / "generated").mkdir(parents=True)
    (dist / "index.html").write_text("app one")
    (dist / "generated/catalog.json").write_text('{"version":1}')
    output = prepare_site(dist, site)
    (output / "catalog.json").write_text('{"version":2}')
    (output / "old-event.json").write_text("frozen snapshot")
    (dist / "index.html").write_text("app two")
    assert prepare_site(dist, site) == output
    assert (site / "index.html").read_text() == "app two"
    assert json.loads((output / "catalog.json").read_text())["version"] == 2
    assert (output / "old-event.json").read_text() == "frozen snapshot"


def test_only_one_publisher_can_run_and_lock_releases_after_failure(tmp_path):
    lock = tmp_path / "publisher.lock"
    with pytest.raises(ValueError, match="stop"), publication_lock(lock):
        with pytest.raises(RuntimeError, match="already running"), publication_lock(lock):
            pytest.fail("second publisher acquired the lock")
        raise ValueError("stop")
    with publication_lock(lock):
        pass


def test_public_deployment_contains_no_request_handler_or_backend_bindings():
    config = tomllib.loads((Path(__file__).parents[1] / "wrangler.toml").read_text())
    assert config["assets"]["directory"] == "./dist"
    assert not {"main", "services", "d1_databases", "workflows"} & config.keys()
    assert "run_worker_first" not in config["assets"]


def test_watcher_retries_source_and_deployment_failures_before_success(tmp_path, monkeypatch):
    import publish

    first = SimpleNamespace(season_events=lambda *_: SimpleNamespace(status=200, data={"events": []}))
    monkeypatch.setitem(
        sys.modules, "warehouse.ingest.client", SimpleNamespace(FtcEventsClient=lambda: nullcontext(first))
    )
    monkeypatch.setattr(publish.httpx, "Client", lambda **_: nullcontext(None))
    monkeypatch.setattr(publish, "STATE", tmp_path)
    monkeypatch.setattr(publish, "prepare_site", lambda *_: tmp_path / "site/generated")
    monkeypatch.setattr(publish, "build_engine", lambda *_: {})
    attempts, deploys = [], []

    def export(*args, **kwargs):
        attempts.append("export")
        if len(attempts) == 1:
            raise ValueError("source unavailable")
        return {"events": []}

    def deploy(*args):
        deploys.append("deploy")
        if len(deploys) == 1:
            raise subprocess.CalledProcessError(1, "wrangler")
        return True

    def sleep(_):
        if len(attempts) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(publish, "export_catalog", export)
    monkeypatch.setattr(publish, "deploy_if_changed", deploy)
    monkeypatch.setattr(publish.time, "sleep", sleep)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8787",
        season=2025,
        region="USPA",
        label="Test",
        deploy=True,
        watch=True,
        interval_s=60,
    )
    with pytest.raises(KeyboardInterrupt):
        publish.run_publisher(args)
    assert len(attempts) == 3
    assert len(deploys) == 2
