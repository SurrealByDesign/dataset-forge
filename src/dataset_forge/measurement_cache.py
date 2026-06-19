"""Internal disk-backed cache for image measurements."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENV_CACHE_DIR = "DATASET_FORGE_MEASUREMENT_CACHE_DIR"
ENV_DISABLE_CACHE = "DATASET_FORGE_DISABLE_MEASUREMENT_CACHE"
CACHE_FILENAME = "measurements.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurement_cache (
    cache_key TEXT PRIMARY KEY,
    file_sha256 TEXT NOT NULL,
    measurement_schema_version INTEGER NOT NULL,
    texture_measurement_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
)
"""


def cache_is_enabled() -> bool:
    """Return True when the opt-in disk cache should be used."""
    if os.environ.get(ENV_DISABLE_CACHE) == "1":
        return False
    return bool(os.environ.get(ENV_CACHE_DIR))


def cache_database_path() -> Path | None:
    """Return the configured SQLite path, or None when caching is disabled."""
    if not cache_is_enabled():
        return None
    configured = os.environ.get(ENV_CACHE_DIR)
    if not configured:
        return None
    return Path(configured).expanduser().resolve() / CACHE_FILENAME


def file_sha256(path: Path) -> str:
    """Hash image bytes for content-addressed cache invalidation."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cache_key(
    file_hash: str,
    measurement_schema_version: int,
    texture_measurement_version: str,
) -> str:
    """Build a content- and version-addressed cache key."""
    key_material = {
        "kind": "image-measurements",
        "file_sha256": file_hash,
        "measurement_schema_version": measurement_schema_version,
        "texture_measurement_version": texture_measurement_version,
    }
    encoded = json.dumps(key_material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def read_cache_payload(
    cache_key: str,
    file_hash: str,
    measurement_schema_version: int,
    texture_measurement_version: str,
) -> dict[str, Any] | None:
    """Read a cached measurement payload, returning None on any cache problem."""
    db_path = cache_database_path()
    if db_path is None:
        return None
    try:
        with closing(_connect(db_path)) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                """
                SELECT payload_json
                FROM measurement_cache
                WHERE cache_key = ?
                  AND file_sha256 = ?
                  AND measurement_schema_version = ?
                  AND texture_measurement_version = ?
                """,
                (
                    cache_key,
                    file_hash,
                    measurement_schema_version,
                    texture_measurement_version,
                ),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None

    if row is None:
        return None

    try:
        payload = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_cache_payload(
    cache_key: str,
    file_hash: str,
    measurement_schema_version: int,
    texture_measurement_version: str,
    payload: dict[str, Any],
) -> None:
    """Write a measurement payload, ignoring cache failures."""
    db_path = cache_database_path()
    if db_path is None:
        return
    try:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with closing(_connect(db_path)) as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO measurement_cache (
                    cache_key,
                    file_sha256,
                    measurement_schema_version,
                    texture_measurement_version,
                    payload_json,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    file_hash,
                    measurement_schema_version,
                    texture_measurement_version,
                    payload_json,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
    except (TypeError, OSError, sqlite3.Error):
        return


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_SCHEMA)


__all__ = [
    "CACHE_FILENAME",
    "ENV_CACHE_DIR",
    "ENV_DISABLE_CACHE",
    "build_cache_key",
    "cache_database_path",
    "cache_is_enabled",
    "file_sha256",
    "read_cache_payload",
    "write_cache_payload",
]
