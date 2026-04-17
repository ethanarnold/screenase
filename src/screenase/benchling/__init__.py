"""Benchling App-shaped subpackage.

Demonstrates how Screenase maps to Benchling's data model (Requests, Results,
Entries) and how webhook handlers would be wired. No live Benchling calls —
handlers read mock webhook payloads from `fixtures/` and return JSON-serializable
dicts shaped like Benchling API payloads.

See `README.md` and the top-level `docs/benchling_mapping.md` for semantics.
"""

from screenase.benchling.entities import (
    design_to_benchling_request,
    effects_to_benchling_entry,
    results_to_benchling_results,
)

__all__ = [
    "design_to_benchling_request",
    "effects_to_benchling_entry",
    "results_to_benchling_results",
]
