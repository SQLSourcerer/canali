"""Dispatch races, crash recovery and coalescing against the actual SQLite SQL."""

import asyncio
from types import SimpleNamespace

import pytest
from dispatch import CLAIM, advance_job, dispatch, instance_id, retry_job, run_job
from engine_version import ENGINE_VERSION
from test_season import Database


class Workflows:
    def __init__(self):
        self.instances = {}
        self.fail_after_create = False

    async def ensure(self, identifier, payload):
        await asyncio.sleep(0)
        self.instances.setdefault(identifier, SimpleNamespace(status="running", payload=payload))
        if self.fail_after_create:
            self.fail_after_create = False
            raise RuntimeError("lost response")

    async def status(self, identifier):
        await asyncio.sleep(0)
        return self.instances[identifier].status

    async def restart(self, identifier):
        self.instances[identifier].status = "running"


def setup():
    db = Database()
    db.sql.execute("INSERT INTO forecast_input VALUES ('TEST', 1, '{}')")
    return db, Workflows()


def tick(db, workflows):
    asyncio.run(dispatch(db, workflows))


def job(db):
    return db.sql.execute("SELECT * FROM forecast_job").fetchone()


def test_repeated_and_concurrent_ticks_create_one_instance():
    db, workflows = setup()

    async def race():
        await asyncio.gather(dispatch(db, workflows), dispatch(db, workflows))

    asyncio.run(race())
    for _ in range(3):
        tick(db, workflows)
    assert len(workflows.instances) == 1
    assert job(db)["status"] == "running"
    # The losing dispatcher cannot claim an already active event.
    assert db.sql.execute(CLAIM, (ENGINE_VERSION, 0, "loser", "TEST", 1)).fetchone() is None


def test_dispatch_recovers_before_and_after_creation():
    db, workflows = setup()
    identifier = instance_id("TEST", 1, ENGINE_VERSION)
    db.sql.execute(CLAIM, (ENGINE_VERSION, 0, identifier, "TEST", 1))
    workflows.fail_after_create = True
    with pytest.raises(RuntimeError, match="dispatch failed"):
        tick(db, workflows)
    assert job(db)["status"] == "pending"
    tick(db, workflows)
    assert len(workflows.instances) == 1
    assert job(db)["status"] == "running"


def test_one_event_failure_does_not_prevent_other_dispatches():
    db, workflows = setup()
    db.sql.execute("INSERT INTO forecast_input VALUES ('OTHER', 1, '{}')")
    workflows.fail_after_create = True
    with pytest.raises(RuntimeError, match="dispatch failed"):
        tick(db, workflows)
    assert len(workflows.instances) == 2
    tick(db, workflows)
    assert {r[0] for r in db.sql.execute("SELECT status FROM forecast_job")} == {"running"}


def test_new_inputs_coalesce_until_active_instance_stops():
    db, workflows = setup()
    tick(db, workflows)
    old = job(db)["instance_id"]
    db.sql.execute("UPDATE forecast_input SET revision = 2")
    tick(db, workflows)
    db.sql.execute("UPDATE forecast_input SET revision = 3")
    tick(db, workflows)
    assert len(workflows.instances) == 1
    workflows.instances[old].status = "complete"
    tick(db, workflows)
    assert job(db)["input_revision"] == 3
    assert len(workflows.instances) == 2
    # A delayed old instance is harmless after ownership changes.
    assert asyncio.run(advance_job(db, workflows.instances[old].payload)) == "superseded"


@pytest.mark.parametrize("outcome", ["complete", "exhausted"])
def test_settled_revision_is_not_recreated_after_retention(outcome):
    db, workflows = setup()
    tick(db, workflows)
    identifier = job(db)["instance_id"]
    db.sql.execute(
        "INSERT INTO forecast_state(event_code, input_revision, engine_version, status) VALUES ('TEST', 1, ?, ?)",
        (ENGINE_VERSION, outcome),
    )
    workflows.instances[identifier].status = "complete"
    tick(db, workflows)
    workflows.instances.clear()
    tick(db, workflows)
    assert not workflows.instances
    assert job(db)["status"] == outcome


def test_failed_job_stays_failed_until_explicit_restart_or_new_input():
    db, workflows = setup()
    tick(db, workflows)
    identifier = job(db)["instance_id"]
    workflows.instances[identifier].status = "errored"
    tick(db, workflows)
    tick(db, workflows)
    assert len(workflows.instances) == 1
    assert job(db)["status"] == "errored"
    assert asyncio.run(retry_job(db, workflows, "TEST"))[1] == 200
    assert job(db)["status"] == "running"


def test_long_run_continues_serially_with_a_new_generation():
    db, workflows = setup()
    tick(db, workflows)
    identifier = job(db)["instance_id"]
    workflows.instances[identifier].status = "complete"
    tick(db, workflows)
    assert job(db)["generation"] == 1
    assert job(db)["instance_id"] != identifier
    assert len(workflows.instances) == 2


def test_queued_old_revision_and_engine_cannot_initialize_checkpoint():
    db, workflows = setup()
    tick(db, workflows)
    payload = next(iter(workflows.instances.values())).payload
    db.sql.execute("UPDATE forecast_input SET revision = 2")
    assert asyncio.run(advance_job(db, payload)) == "superseded"
    db.sql.execute("UPDATE forecast_input SET revision = 1")
    assert asyncio.run(advance_job(db, {**payload, "engine": "old"})) == "superseded"
    assert db.sql.execute("SELECT * FROM forecast_state").fetchone() is None


def test_workflow_runs_bounded_steps_and_resumes_real_forecast():
    import json
    from pathlib import Path

    db, workflows = setup()
    document = json.loads((Path(__file__).parents[1] / "fixtures/forecast.json").read_text())
    document.update(min_iterations=32, max_iterations=32, tolerance=0.5)
    db.sql.execute("UPDATE forecast_input SET document = ?", (json.dumps(document),))
    tick(db, workflows)
    payload = next(iter(workflows.instances.values())).payload

    class Steps:
        def do(self, _name):
            return lambda fn: fn

    assert asyncio.run(run_job(db, payload, Steps())) == "complete"
    assert db.sql.execute("SELECT status FROM forecast_state").fetchone()[0] == "complete"
