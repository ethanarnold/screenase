"""Tests for URL-safe config encoding / decoding."""

from __future__ import annotations

from screenase.share import decode_config, encode_config


def test_roundtrip_default_config(cfg) -> None:
    blob = encode_config(cfg)
    # Should be URL-safe (no padding, no +/) and compact
    assert "=" not in blob
    assert "+" not in blob
    assert "/" not in blob
    decoded = decode_config(blob)
    assert decoded.model_dump() == cfg.model_dump()


def test_blob_stays_under_url_limit(cfg) -> None:
    # Default config should comfortably round-trip in a URL.
    blob = encode_config(cfg)
    assert len(blob) < 1500


def test_invalid_blob_raises() -> None:
    import pytest

    with pytest.raises(Exception, match=""):  # noqa: B017 — any decode failure is acceptable here
        decode_config("!!!not-a-valid-blob!!!")
