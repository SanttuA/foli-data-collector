from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


LOCAL_SCHEMES = {"", "file"}


def _sqlite_path_from_url(database_url: str) -> str:
    if database_url == ":memory:":
        return database_url
    parsed = urlparse(database_url)
    if parsed.scheme == "file":
        if parsed.netloc and parsed.path:
            return f"//{parsed.netloc}{parsed.path}"
        return parsed.path or parsed.netloc
    return database_url


def is_local_database_url(database_url: str) -> bool:
    if database_url == ":memory:":
        return True
    parsed = urlparse(database_url)
    return parsed.scheme in LOCAL_SCHEMES and not database_url.startswith(("libsql://", "http://", "https://"))


def connect_database(database_url: str, auth_token: str | None = None) -> Any:
    if is_local_database_url(database_url):
        path = _sqlite_path_from_url(database_url)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    try:
        import libsql
    except ImportError as exc:
        raise RuntimeError(
            "Remote Turso/libSQL URLs require the `libsql` package. "
            "Install dependencies with `pip install -r requirements.txt`."
        ) from exc
    return libsql.connect(database_url, auth_token=auth_token)


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS collector_polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        attempted_at_utc TEXT NOT NULL,
        collected_at_utc TEXT,
        foli_server_time_utc TEXT,
        status TEXT NOT NULL,
        ok INTEGER NOT NULL DEFAULT 0,
        http_status INTEGER,
        row_count INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER,
        error_text TEXT,
        gap_seconds_since_previous_success INTEGER,
        created_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_collector_polls_source_time
    ON collector_polls(source, attempted_at_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS vehicle_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL REFERENCES collector_polls(id) ON DELETE CASCADE,
        vehicle_id TEXT NOT NULL,
        recorded_at_utc TEXT,
        valid_until_utc TEXT,
        line_ref TEXT,
        direction_ref TEXT,
        origin_aimed_departure_time_utc TEXT,
        origin_aimed_departure_unix INTEGER,
        trip_match_key TEXT,
        is_gtfs_matchable INTEGER NOT NULL DEFAULT 0,
        published_line_name TEXT,
        operator_ref TEXT,
        origin_ref TEXT,
        origin_name TEXT,
        destination_ref TEXT,
        destination_name TEXT,
        destination_aimed_arrival_time_utc TEXT,
        destination_aimed_arrival_unix INTEGER,
        latitude REAL,
        longitude REAL,
        delay_text TEXT,
        delay_seconds INTEGER,
        in_congestion INTEGER,
        in_panic INTEGER,
        monitored INTEGER,
        vehicle_at_stop INTEGER,
        next_stop_point_ref TEXT,
        next_stop_point_name TEXT,
        next_destination_display TEXT,
        next_aimed_arrival_time_utc TEXT,
        next_expected_arrival_time_utc TEXT,
        next_aimed_departure_time_utc TEXT,
        next_expected_departure_time_utc TEXT,
        created_at_utc TEXT NOT NULL,
        UNIQUE(poll_id, vehicle_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_vehicle_observations_trip_match
    ON vehicle_observations(trip_match_key, recorded_at_utc)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_vehicle_observations_vehicle_time
    ON vehicle_observations(vehicle_id, recorded_at_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS service_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL REFERENCES collector_polls(id) ON DELETE CASCADE,
        alert_type TEXT NOT NULL,
        source_alert_id TEXT,
        line_ref TEXT,
        cause TEXT,
        effect TEXT,
        priority INTEGER,
        is_active INTEGER,
        departure_time_utc TEXT,
        validity_start_utc TEXT,
        validity_end_utc TEXT,
        icon TEXT,
        header TEXT,
        message TEXT,
        information TEXT,
        affected_routes_json TEXT,
        affected_stops_json TEXT,
        categories_json TEXT,
        repeat_json TEXT,
        stops_json TEXT,
        created_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_service_alerts_type_active
    ON service_alerts(alert_type, is_active)
    """,
    """
    CREATE TABLE IF NOT EXISTS gtfs_archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        downloaded_at_utc TEXT NOT NULL,
        download_service_date TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        local_path TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        byte_size INTEGER NOT NULL,
        etag TEXT,
        last_modified TEXT,
        source_url TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gtfs_archives_last_modified
    ON gtfs_archives(last_modified)
    """,
    """
    CREATE TABLE IF NOT EXISTS collector_state (
        source TEXT PRIMARY KEY,
        last_success_at_utc TEXT,
        last_attempted_at_utc TEXT,
        last_status TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        next_due_at_utc TEXT,
        updated_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collector_lock (
        lock_name TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        acquired_at_utc TEXT NOT NULL,
        heartbeat_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL
    )
    """,
]


def init_schema(conn: Any) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()


def row_to_dict(row: Any, columns: list[str] | tuple[str, ...]) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(zip(columns, row, strict=False))


def first_column(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return row[0]
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]

