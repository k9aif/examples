"""
Deterministic services — zero LLM imports, enforced by tests/test_deterministic_purity.py.

Ordinary Python modules against a plain Postgres connection (petstore/services/db.py).
No agent, no SDK, no model client anywhere in this package.
"""
