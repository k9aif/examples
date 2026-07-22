"""
Plain Postgres connection helper for petstore/services/.

Deliberately not routed through k9_aif_abb's persistence ABBs — those
exist for agents/orchestrators; these are plain deterministic services,
outside the ABB/SBB hierarchy entirely, and depending on nothing but a
DB driver is what keeps that true. No LLM, no SDK, no agent imports here
or anywhere else in this package — enforced by test_deterministic_purity.py.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extensions

_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "petstore"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )


@contextmanager
def get_cursor(commit: bool = False) -> Iterator[psycopg2.extensions.cursor]:
    """Yield a cursor pinned to the petstore schema's search_path, in its own connection."""
    conn = _connect()
    schema = os.environ.get("POSTGRES_SCHEMA", "petstore")
    if not _VALID_IDENTIFIER.match(schema):
        raise ValueError(f"Invalid POSTGRES_SCHEMA value: {schema!r}")
    try:
        cur = conn.cursor()
        cur.execute(f"SET search_path TO {schema}, public")
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()
