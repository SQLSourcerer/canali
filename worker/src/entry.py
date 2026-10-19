"""Local-only D1 adapter for the event-computation prototype."""

import json
import re
from urllib.parse import urlparse

from compute import compute, validate
from workers import Response, WorkerEntrypoint

MAX_BODY = 512_000


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if self.env.LOCAL_PROTOTYPE != "true":
            return Response.json({"error": "local prototype is disabled"}, status=403)
        path = urlparse(request.url).path
        if path == "/health" and request.method == "GET":
            import numpy
            import scipy

            return Response.json({"status": "ok", "numpy": numpy.__version__, "scipy": scipy.__version__})
        route = re.fullmatch(r"/events/([A-Za-z0-9_-]{1,64})(/run)?", path)
        if route is None:
            return Response.json({"error": "route not found"}, status=404)
        code, run = route.groups()
        db = self.env.DB
        try:
            if request.method == "PUT" and not run:
                body = await request.text()
                if len(body.encode()) > MAX_BODY:
                    return Response.json({"error": "input exceeds 512000 bytes"}, status=413)
                document = json.loads(body)
                validate(document)
                row = (
                    await db.prepare(
                        "INSERT INTO event_input(event_code, revision, document) VALUES (?, 1, ?) "
                        "ON CONFLICT(event_code) DO UPDATE SET revision = revision + 1, document = excluded.document "
                        "RETURNING revision"
                    )
                    .bind(code, json.dumps(document, allow_nan=False))
                    .first()
                )
                return Response.json({"event": code, "revision": row.revision})
            if request.method == "POST" and run:
                row = (
                    await db.prepare("SELECT revision, document FROM event_input WHERE event_code = ?")
                    .bind(code)
                    .first()
                )
                if row is None:
                    return Response.json({"error": "event not found"}, status=404)
                revision = row.revision
                result = json.dumps(compute(json.loads(row.document)), allow_nan=False)
                saved = (
                    await db.prepare(
                        "INSERT INTO event_result(event_code, input_revision, document) "
                        "SELECT event_code, revision, ? FROM event_input WHERE event_code = ? AND revision = ? "
                        "ON CONFLICT(event_code) DO UPDATE SET input_revision = excluded.input_revision, "
                        "document = excluded.document, computed_at = CURRENT_TIMESTAMP RETURNING input_revision"
                    )
                    .bind(result, code, revision)
                    .first()
                )
                if saved is None:
                    return Response.json({"error": "input changed; rerun computation"}, status=409)
                return Response.json({"event": code, "revision": revision, "result": json.loads(result)})
            if request.method == "GET" and not run:
                row = (
                    await db.prepare(
                        "SELECT r.document, r.input_revision FROM event_result r JOIN event_input i "
                        "ON i.event_code = r.event_code AND i.revision = r.input_revision WHERE r.event_code = ?"
                    )
                    .bind(code)
                    .first()
                )
                if row is None:
                    return Response.json({"error": "no result for current inputs"}, status=404)
                return Response.json(
                    {"event": code, "revision": row.input_revision, "result": json.loads(row.document)}
                )
            return Response.json({"error": "method not allowed"}, status=405)
        except (ValueError, KeyError, TypeError) as exc:
            return Response.json({"error": str(exc)}, status=400)
