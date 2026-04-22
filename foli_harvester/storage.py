from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .db import first_column, init_schema, row_to_dict
from .timeutils import isoformat_z, utc_now


POLL_COLUMNS = [
    "id",
    "source",
    "attempted_at_utc",
    "collected_at_utc",
    "foli_server_time_utc",
    "status",
    "ok",
    "http_status",
    "row_count",
    "latency_ms",
    "error_text",
    "gap_seconds_since_previous_success",
    "created_at_utc",
]

STATE_COLUMNS = [
    "source",
    "last_success_at_utc",
    "last_attempted_at_utc",
    "last_status",
    "consecutive_failures",
    "next_due_at_utc",
    "updated_at_utc",
]

GTFS_COLUMNS = [
    "id",
    "downloaded_at_utc",
    "download_service_date",
    "stored_filename",
    "local_path",
    "sha256",
    "byte_size",
    "etag",
    "last_modified",
    "source_url",
    "created_at_utc",
]

LOCK_COLUMNS = ["lock_name", "owner_id", "acquired_at_utc", "heartbeat_at_utc", "expires_at_utc"]


@dataclass(frozen=True)
class PollRecord:
    source: str
    attempted_at_utc: str
    collected_at_utc: str | None
    foli_server_time_utc: str | None
    status: str
    ok: bool
    http_status: int | None
    row_count: int
    latency_ms: int | None
    error_text: str | None
    gap_seconds_since_previous_success: int | None


class Storage:
    def __init__(self, conn: Any):
        self.conn = conn

    def init_schema(self) -> None:
        init_schema(self.conn)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        if hasattr(self.conn, "rollback"):
            self.conn.rollback()

    def record_poll(self, poll: PollRecord) -> int:
        row = self.conn.execute(
            """
            INSERT INTO collector_polls (
                source,
                attempted_at_utc,
                collected_at_utc,
                foli_server_time_utc,
                status,
                ok,
                http_status,
                row_count,
                latency_ms,
                error_text,
                gap_seconds_since_previous_success,
                created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                poll.source,
                poll.attempted_at_utc,
                poll.collected_at_utc,
                poll.foli_server_time_utc,
                poll.status,
                1 if poll.ok else 0,
                poll.http_status,
                poll.row_count,
                poll.latency_ms,
                poll.error_text,
                poll.gap_seconds_since_previous_success,
                isoformat_z(utc_now()),
            ),
        ).fetchone()
        return int(first_column(row))

    def insert_vehicle_observations(self, poll_id: int, observations: Iterable[dict[str, Any]]) -> None:
        now = isoformat_z(utc_now())
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO vehicle_observations (
                poll_id,
                vehicle_id,
                recorded_at_utc,
                valid_until_utc,
                line_ref,
                direction_ref,
                origin_aimed_departure_time_utc,
                origin_aimed_departure_unix,
                trip_match_key,
                is_gtfs_matchable,
                published_line_name,
                operator_ref,
                origin_ref,
                origin_name,
                destination_ref,
                destination_name,
                destination_aimed_arrival_time_utc,
                destination_aimed_arrival_unix,
                latitude,
                longitude,
                delay_text,
                delay_seconds,
                in_congestion,
                in_panic,
                monitored,
                vehicle_at_stop,
                next_stop_point_ref,
                next_stop_point_name,
                next_destination_display,
                next_aimed_arrival_time_utc,
                next_expected_arrival_time_utc,
                next_aimed_departure_time_utc,
                next_expected_departure_time_utc,
                created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    poll_id,
                    item["vehicle_id"],
                    item.get("recorded_at_utc"),
                    item.get("valid_until_utc"),
                    item.get("line_ref"),
                    item.get("direction_ref"),
                    item.get("origin_aimed_departure_time_utc"),
                    item.get("origin_aimed_departure_unix"),
                    item.get("trip_match_key"),
                    1 if item.get("is_gtfs_matchable") else 0,
                    item.get("published_line_name"),
                    item.get("operator_ref"),
                    item.get("origin_ref"),
                    item.get("origin_name"),
                    item.get("destination_ref"),
                    item.get("destination_name"),
                    item.get("destination_aimed_arrival_time_utc"),
                    item.get("destination_aimed_arrival_unix"),
                    item.get("latitude"),
                    item.get("longitude"),
                    item.get("delay_text"),
                    item.get("delay_seconds"),
                    _bool_to_db(item.get("in_congestion")),
                    _bool_to_db(item.get("in_panic")),
                    _bool_to_db(item.get("monitored")),
                    _bool_to_db(item.get("vehicle_at_stop")),
                    item.get("next_stop_point_ref"),
                    item.get("next_stop_point_name"),
                    item.get("next_destination_display"),
                    item.get("next_aimed_arrival_time_utc"),
                    item.get("next_expected_arrival_time_utc"),
                    item.get("next_aimed_departure_time_utc"),
                    item.get("next_expected_departure_time_utc"),
                    now,
                )
                for item in observations
            ],
        )

    def insert_service_alerts(self, poll_id: int, alerts: Iterable[dict[str, Any]]) -> None:
        now = isoformat_z(utc_now())
        self.conn.executemany(
            """
            INSERT INTO service_alerts (
                poll_id,
                alert_type,
                source_alert_id,
                line_ref,
                cause,
                effect,
                priority,
                is_active,
                departure_time_utc,
                validity_start_utc,
                validity_end_utc,
                icon,
                header,
                message,
                information,
                affected_routes_json,
                affected_stops_json,
                categories_json,
                repeat_json,
                stops_json,
                created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    poll_id,
                    item["alert_type"],
                    item.get("source_alert_id"),
                    item.get("line_ref"),
                    item.get("cause"),
                    item.get("effect"),
                    item.get("priority"),
                    _bool_to_db(item.get("is_active")),
                    item.get("departure_time_utc"),
                    item.get("validity_start_utc"),
                    item.get("validity_end_utc"),
                    item.get("icon"),
                    item.get("header"),
                    item.get("message"),
                    item.get("information"),
                    item.get("affected_routes_json"),
                    item.get("affected_stops_json"),
                    item.get("categories_json"),
                    item.get("repeat_json"),
                    item.get("stops_json"),
                    now,
                )
                for item in alerts
            ],
        )

    def get_state(self, source: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT source, last_success_at_utc, last_attempted_at_utc, last_status,
                   consecutive_failures, next_due_at_utc, updated_at_utc
            FROM collector_state
            WHERE source = ?
            """,
            (source,),
        ).fetchone()
        return row_to_dict(row, STATE_COLUMNS)

    def upsert_state(
        self,
        *,
        source: str,
        last_success_at_utc: str | None,
        last_attempted_at_utc: str,
        last_status: str,
        consecutive_failures: int,
        next_due_at_utc: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO collector_state (
                source,
                last_success_at_utc,
                last_attempted_at_utc,
                last_status,
                consecutive_failures,
                next_due_at_utc,
                updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_success_at_utc = excluded.last_success_at_utc,
                last_attempted_at_utc = excluded.last_attempted_at_utc,
                last_status = excluded.last_status,
                consecutive_failures = excluded.consecutive_failures,
                next_due_at_utc = excluded.next_due_at_utc,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                source,
                last_success_at_utc,
                last_attempted_at_utc,
                last_status,
                consecutive_failures,
                next_due_at_utc,
                isoformat_z(utc_now()),
            ),
        )

    def find_gtfs_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, downloaded_at_utc, download_service_date, stored_filename, local_path,
                   sha256, byte_size, etag, last_modified, source_url, created_at_utc
            FROM gtfs_archives
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchone()
        return row_to_dict(row, GTFS_COLUMNS)

    def insert_gtfs_archive(self, metadata: dict[str, Any]) -> int:
        row = self.conn.execute(
            """
            INSERT INTO gtfs_archives (
                downloaded_at_utc,
                download_service_date,
                stored_filename,
                local_path,
                sha256,
                byte_size,
                etag,
                last_modified,
                source_url,
                created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                metadata["downloaded_at_utc"],
                metadata["download_service_date"],
                metadata["stored_filename"],
                metadata["local_path"],
                metadata["sha256"],
                metadata["byte_size"],
                metadata.get("etag"),
                metadata.get("last_modified"),
                metadata["source_url"],
                isoformat_z(utc_now()),
            ),
        ).fetchone()
        return int(first_column(row))

    def get_lock(self, lock_name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT lock_name, owner_id, acquired_at_utc, heartbeat_at_utc, expires_at_utc
            FROM collector_lock
            WHERE lock_name = ?
            """,
            (lock_name,),
        ).fetchone()
        return row_to_dict(row, LOCK_COLUMNS)

    def insert_lock(
        self,
        *,
        lock_name: str,
        owner_id: str,
        acquired_at_utc: str,
        heartbeat_at_utc: str,
        expires_at_utc: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO collector_lock (
                lock_name, owner_id, acquired_at_utc, heartbeat_at_utc, expires_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (lock_name, owner_id, acquired_at_utc, heartbeat_at_utc, expires_at_utc),
        )

    def update_lock(
        self,
        *,
        lock_name: str,
        owner_id: str,
        heartbeat_at_utc: str,
        expires_at_utc: str,
        acquired_at_utc: str | None = None,
    ) -> None:
        if acquired_at_utc is None:
            self.conn.execute(
                """
                UPDATE collector_lock
                SET heartbeat_at_utc = ?, expires_at_utc = ?
                WHERE lock_name = ? AND owner_id = ?
                """,
                (heartbeat_at_utc, expires_at_utc, lock_name, owner_id),
            )
            return
        self.conn.execute(
            """
            UPDATE collector_lock
            SET owner_id = ?, acquired_at_utc = ?, heartbeat_at_utc = ?, expires_at_utc = ?
            WHERE lock_name = ?
            """,
            (owner_id, acquired_at_utc, heartbeat_at_utc, expires_at_utc, lock_name),
        )

    def delete_lock(self, *, lock_name: str, owner_id: str) -> None:
        self.conn.execute(
            "DELETE FROM collector_lock WHERE lock_name = ? AND owner_id = ?",
            (lock_name, owner_id),
        )


def _bool_to_db(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0

