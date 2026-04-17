"""Tests for the HMAC-verify helper in `screenase.serve`.

The FastAPI app itself requires the `[serve]` extra; we skip those tests if
fastapi isn't installed. The HMAC logic has no heavy deps and is tested here.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pytest

from screenase.serve import HMAC_ENV, _verify_hmac


def test_verify_hmac_no_secret_skips() -> None:
    os.environ.pop(HMAC_ENV, None)
    assert _verify_hmac(b"{}", None) is True
    assert _verify_hmac(b"{}", "anything") is True


def test_verify_hmac_accepts_correct_signature(monkeypatch) -> None:
    secret = "topsecret"
    monkeypatch.setenv(HMAC_ENV, secret)
    body = b'{"k":1}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_hmac(body, sig) is True


def test_verify_hmac_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setenv(HMAC_ENV, "topsecret")
    assert _verify_hmac(b"{}", "wrong") is False
    assert _verify_hmac(b"{}", None) is False


@pytest.mark.skipif(
    pytest.importorskip("fastapi", reason="fastapi not installed") is None,
    reason="fastapi extra not installed",
)
def test_create_app_has_expected_routes() -> None:
    try:
        from screenase.serve import create_app
    except ImportError:
        pytest.skip("fastapi not installed")
    app = create_app()
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/health" in routes
    assert "/benchling/request_created" in routes
