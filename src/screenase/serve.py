"""FastAPI server that exposes the Benchling-shaped webhook handlers.

Minimal by design: no auth layer beyond an optional shared-secret HMAC hook
(`BENCHLING_HMAC_SECRET` env var). Points directly at the existing handlers
in `screenase.benchling.app` — no logic duplication.

Run locally:
    pip install 'screenase[serve]'
    uvicorn screenase.serve:app --reload

Benchling integration flow: a real tenant would point its `request_created`
webhook URL at `https://…/benchling/request_created` on this server.
"""

import hashlib
import hmac
import os
from typing import Any

from screenase.benchling.app import (
    handle_entry_completed,
    handle_reagent_consumed,
    handle_request_created,
    handle_results_submitted,
)

HMAC_ENV = "BENCHLING_HMAC_SECRET"


def _verify_hmac(body: bytes, signature: str | None) -> bool:
    secret = os.environ.get(HMAC_ENV)
    if not secret:
        return True  # no secret configured → skip (dev mode)
    if not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def create_app():  # pragma: no cover — requires fastapi extra
    """Build the FastAPI app. Lazy-imports fastapi so the core package is free."""
    from fastapi import FastAPI, HTTPException, Request

    app = FastAPI(
        title="Screenase — Benchling webhook server",
        description="Webhook endpoints mirroring benchling.app handlers.",
    )

    async def _run(req: Request, handler) -> dict[str, Any]:
        body = await req.body()
        sig = req.headers.get("X-Benchling-Signature")
        if not _verify_hmac(body, sig):
            raise HTTPException(status_code=401, detail="bad HMAC signature")
        try:
            payload = await req.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        try:
            return handler(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/benchling/request_created")
    async def request_created(req: Request) -> dict[str, Any]:
        return await _run(req, handle_request_created)

    @app.post("/benchling/results_submitted")
    async def results_submitted(req: Request) -> dict[str, Any]:
        return await _run(req, handle_results_submitted)

    @app.post("/benchling/reagent_consumed")
    async def reagent_consumed(req: Request) -> dict[str, Any]:
        return await _run(req, handle_reagent_consumed)

    @app.post("/benchling/entry_completed")
    async def entry_completed(req: Request) -> dict[str, Any]:
        return await _run(req, handle_entry_completed)

    return app


# Lazy module-level `app` — only instantiated if someone imports it (e.g. uvicorn).
def __getattr__(name: str):  # pragma: no cover
    if name == "app":
        return create_app()
    raise AttributeError(name)
