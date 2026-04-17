"""Encode / decode a `ReactionConfig` into a URL-safe query-param blob.

Used by the Streamlit app's shareable-URL feature: a user generates a design,
copies a link like `https://screenase.streamlit.app/?cfg=<blob>`, and a
recipient landing on that URL sees the identical sidebar state.

The blob is a base64url-encoded gzip of the pydantic JSON dump. For a default
k=4 config this lands around ~400 bytes — well under the 2 KB URL limit on
every browser still in use.
"""

from __future__ import annotations

import base64
import gzip
import json

from screenase.config import ReactionConfig


def encode_config(cfg: ReactionConfig) -> str:
    raw = json.dumps(cfg.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw)
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")


def decode_config(blob: str) -> ReactionConfig:
    padding = "=" * (-len(blob) % 4)
    compressed = base64.urlsafe_b64decode(blob + padding)
    raw = gzip.decompress(compressed)
    data = json.loads(raw.decode("utf-8"))
    return ReactionConfig.model_validate(data)
