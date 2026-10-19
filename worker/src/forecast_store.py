"""D1 checkpoint publication guarded by input revision, engine version and step."""

import json

from engine_version import ENGINE_VERSION
from forecast import advance
from snapshot import EventSnapshot

MAX_BODY = 512_000

INITIALIZE = (
    "INSERT INTO forecast_state(event_code, input_revision, engine_version) "
    "SELECT event_code, revision, ? FROM forecast_input WHERE event_code = ? AND revision = ? "
    "ON CONFLICT(event_code) DO UPDATE SET input_revision = excluded.input_revision, "
    "engine_version = excluded.engine_version, step = 0, checkpoint = '{}', status = 'running', result = NULL "
    "WHERE forecast_state.input_revision != excluded.input_revision "
    "OR forecast_state.engine_version != excluded.engine_version"
)
READ_STATE = (
    "SELECT s.* FROM forecast_state s JOIN forecast_input i "
    "ON i.event_code = s.event_code AND i.revision = s.input_revision "
    "WHERE s.event_code = ? AND s.engine_version = ?"
)
SAVE_STATE = (
    "UPDATE forecast_state SET checkpoint = ?, status = ?, result = ?, step = step + 1 "
    "WHERE event_code = ? AND input_revision = ? AND engine_version = ? AND step = ? "
    "AND EXISTS (SELECT 1 FROM forecast_input WHERE event_code = ? AND revision = ?) RETURNING step"
)


def stored_report(row) -> dict:
    report = json.loads(row.result) if row.result else {"status": "running", "iterations": 0, "result": None}
    return {"event": row.event_code, "revision": row.input_revision, "step": row.step, **report}


async def handle(db, request, code: str, run: bool) -> tuple[dict, int]:
    if request.method == "PUT" and not run:
        return await upload(db, request, code)
    if request.method == "GET" and not run:
        row = await db.prepare(READ_STATE).bind(code, ENGINE_VERSION).first()
        if row is None:
            return {"error": "no forecast for current inputs and engine"}, 404
        return stored_report(row), 200
    if request.method != "POST" or not run:
        return {"error": "method not allowed"}, 405
    return await step(db, code)


async def upload(db, request, code: str) -> tuple[dict, int]:
    body = await request.text()
    if len(body.encode()) > MAX_BODY:
        return {"error": "input exceeds 512000 bytes"}, 413
    snapshot = EventSnapshot.model_validate_json(body)
    document = snapshot.model_dump_json()
    row = (
        await db.prepare(
            "INSERT INTO forecast_input(event_code, revision, document) VALUES (?, 1, ?) "
            "ON CONFLICT(event_code) DO UPDATE SET revision = revision + 1, "
            "document = excluded.document RETURNING revision"
        )
        .bind(code, document)
        .first()
    )
    return {"event": code, "revision": row.revision}, 200


async def step(db, code: str) -> tuple[dict, int]:
    source = await db.prepare("SELECT revision, document FROM forecast_input WHERE event_code = ?").bind(code).first()
    if source is None:
        return {"error": "event not found"}, 404
    revision = source.revision
    await db.prepare(INITIALIZE).bind(ENGINE_VERSION, code, revision).run()
    state = await db.prepare(READ_STATE).bind(code, ENGINE_VERSION).first()
    if state is None or state.input_revision != revision:
        return {"error": "input changed; retry the current revision"}, 409
    if state.status != "running":
        return stored_report(state), 200
    snapshot = EventSnapshot.model_validate_json(source.document)
    checkpoint, report = advance(snapshot, json.loads(state.checkpoint))
    saved = (
        await db.prepare(SAVE_STATE)
        .bind(
            json.dumps(checkpoint, allow_nan=False),
            report["status"],
            json.dumps(report, allow_nan=False),
            code,
            revision,
            ENGINE_VERSION,
            state.step,
            code,
            revision,
        )
        .first()
    )
    if saved is None:
        return {"error": "input or checkpoint changed; retry the current revision"}, 409
    status = 202 if report["status"] == "running" else 200
    return {"event": code, "revision": revision, "step": saved.step, **report}, status
