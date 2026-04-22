from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .client import FoliClient
from .config import Config
from .db import connect_database
from .gtfs import sha256_bytes, write_gtfs_archive
from .lock import CollectorLock
from .parsers import parse_alerts_payload, parse_vm_payload
from .storage import PollRecord, Storage
from .timeutils import add_seconds, isoformat_z, parse_utc, seconds_between, utc_now


SOURCE_VM = "siri_vm"
SOURCE_ALERTS = "siri_alerts"
SOURCE_GTFS = "gtfs"


@dataclass(frozen=True)
class Job:
    source: str
    interval_seconds: int
    run: Callable[[], None]


class Collector:
    def __init__(self, config: Config):
        self.config = config
        self.conn = connect_database(config.database_url, config.auth_token)
        self.storage = Storage(self.conn)
        self.client = FoliClient(
            base_url=config.foli_base_url,
            user_agent=config.foli_user_agent,
            timeout_seconds=config.request_timeout_seconds,
        )
        self.lock = CollectorLock(
            storage=self.storage,
            owner_id=config.collector_instance_id,
            ttl_seconds=config.lock_ttl_seconds,
        )
        self.logger = logging.getLogger(__name__)
        self.should_stop = False
        self.local_next_due: dict[str, datetime] = {}
        self.local_failures: dict[str, int] = {}
        self.jobs = [
            Job(SOURCE_VM, config.poll_vm_seconds, self.collect_vm),
            Job(SOURCE_ALERTS, config.poll_alerts_seconds, self.collect_alerts),
            Job(SOURCE_GTFS, config.gtfs_interval_seconds, self.collect_gtfs),
        ]

    def run_forever(self) -> int:
        self.storage.init_schema()
        if not self.lock.acquire():
            current = self.storage.get_lock(self.lock.lock_name)
            owner = current["owner_id"] if current else "unknown"
            self.logger.error("collector lock is owned by %s; exiting", owner)
            return 2

        self._install_signal_handlers()
        next_heartbeat = time.monotonic() + self.config.lock_heartbeat_seconds
        self.logger.info("collector started as %s", self.config.collector_instance_id)
        try:
            while not self.should_stop:
                now = utc_now()
                for job in self.jobs:
                    try:
                        if self._is_due(job, now):
                            self._run_job(job)
                    except Exception as exc:
                        failures = self.local_failures.get(job.source, 0) + 1
                        self.local_failures[job.source] = failures
                        self.local_next_due[job.source] = utc_now() + self._backoff_delta(failures)
                        self.logger.warning("could not check %s due state: %s", job.source, exc)

                if time.monotonic() >= next_heartbeat:
                    try:
                        if not self.lock.renew():
                            self.logger.error("collector lock was lost; exiting")
                            return 3
                    except Exception as exc:
                        self.logger.warning("collector lock renewal failed; retrying: %s", exc)
                    next_heartbeat = time.monotonic() + self.config.lock_heartbeat_seconds

                self._sleep_until_next_due()
        finally:
            try:
                self.lock.release()
            except Exception:
                self.logger.exception("failed to release collector lock")
        return 0

    def collect_vm(self) -> None:
        attempted_at = utc_now()
        state = self.storage.get_state(SOURCE_VM)
        try:
            response = self.client.get_json("/siri/vm")
            parsed = parse_vm_payload(response.payload)
            ok = parsed.status == "OK"
            observations = parsed.observations if ok else []
            error_text = None if ok else f"SIRI VM status {parsed.status}"
            poll_id = self._record_poll_and_state(
                source=SOURCE_VM,
                attempted_at=attempted_at,
                collected_at=utc_now(),
                foli_server_time_utc=parsed.server_time_utc,
                status=parsed.status,
                ok=ok,
                http_status=response.http_status,
                row_count=len(observations),
                latency_ms=response.latency_ms,
                error_text=error_text,
                interval_seconds=self.config.poll_vm_seconds,
                previous_state=state,
            )
            if observations:
                self.storage.insert_vehicle_observations(poll_id, observations)
            self.storage.commit()
            self.logger.info("vm poll status=%s vehicles=%s", parsed.status, len(observations))
        except Exception as exc:
            self.storage.rollback()
            self._record_failure(
                source=SOURCE_VM,
                attempted_at=attempted_at,
                status="ERROR",
                error_text=str(exc),
                interval_seconds=self.config.poll_vm_seconds,
                previous_state=state,
            )
            self.logger.warning("vm poll failed: %s", exc)

    def collect_alerts(self) -> None:
        attempted_at = utc_now()
        state = self.storage.get_state(SOURCE_ALERTS)
        try:
            response = self.client.get_json("/alerts")
            parsed = parse_alerts_payload(response.payload)
            poll_id = self._record_poll_and_state(
                source=SOURCE_ALERTS,
                attempted_at=attempted_at,
                collected_at=utc_now(),
                foli_server_time_utc=parsed.server_time_utc,
                status="OK",
                ok=True,
                http_status=response.http_status,
                row_count=len(parsed.alerts),
                latency_ms=response.latency_ms,
                error_text=None,
                interval_seconds=self.config.poll_alerts_seconds,
                previous_state=state,
            )
            if parsed.alerts:
                self.storage.insert_service_alerts(poll_id, parsed.alerts)
            self.storage.commit()
            self.logger.info("alerts poll rows=%s", len(parsed.alerts))
        except Exception as exc:
            self.storage.rollback()
            self._record_failure(
                source=SOURCE_ALERTS,
                attempted_at=attempted_at,
                status="ERROR",
                error_text=str(exc),
                interval_seconds=self.config.poll_alerts_seconds,
                previous_state=state,
            )
            self.logger.warning("alerts poll failed: %s", exc)

    def collect_gtfs(self) -> None:
        attempted_at = utc_now()
        state = self.storage.get_state(SOURCE_GTFS)
        source_url = f"{self.config.foli_base_url}/gtfs/gtfs.zip"
        try:
            response = self.client.get_bytes("/gtfs/gtfs.zip")
            body_sha = sha256_bytes(response.body)
            existing = self.storage.find_gtfs_by_sha256(body_sha)
            if existing:
                self._record_poll_and_state(
                    source=SOURCE_GTFS,
                    attempted_at=attempted_at,
                    collected_at=utc_now(),
                    foli_server_time_utc=None,
                    status="OK_DUPLICATE",
                    ok=True,
                    http_status=response.http_status,
                    row_count=0,
                    latency_ms=response.latency_ms,
                    error_text=f"GTFS content already archived as {existing['stored_filename']}",
                    interval_seconds=self.config.gtfs_interval_seconds,
                    previous_state=state,
                )
                self.storage.commit()
                self.logger.info("gtfs unchanged sha256=%s", body_sha)
                return

            metadata = write_gtfs_archive(
                body=response.body,
                headers=response.headers,
                gtfs_dir=self.config.gtfs_dir,
                source_url=source_url,
            )
            self._record_poll_and_state(
                source=SOURCE_GTFS,
                attempted_at=attempted_at,
                collected_at=utc_now(),
                foli_server_time_utc=None,
                status="OK",
                ok=True,
                http_status=response.http_status,
                row_count=1,
                latency_ms=response.latency_ms,
                error_text=None,
                interval_seconds=self.config.gtfs_interval_seconds,
                previous_state=state,
            )
            self.storage.insert_gtfs_archive(metadata.as_dict())
            self.storage.commit()
            self.logger.info("archived gtfs %s", metadata.stored_filename)
        except Exception as exc:
            self.storage.rollback()
            self._record_failure(
                source=SOURCE_GTFS,
                attempted_at=attempted_at,
                status="ERROR",
                error_text=str(exc),
                interval_seconds=self.config.gtfs_interval_seconds,
                previous_state=state,
            )
            self.logger.warning("gtfs poll failed: %s", exc)

    def _record_poll_and_state(
        self,
        *,
        source: str,
        attempted_at: datetime,
        collected_at: datetime,
        foli_server_time_utc: str | None,
        status: str,
        ok: bool,
        http_status: int | None,
        row_count: int,
        latency_ms: int | None,
        error_text: str | None,
        interval_seconds: int,
        previous_state: dict[str, object] | None,
    ) -> int:
        previous_success = (
            str(previous_state["last_success_at_utc"])
            if previous_state and previous_state.get("last_success_at_utc")
            else None
        )
        gap_seconds = seconds_between(collected_at, previous_success) if ok else None
        failures = 0 if ok else _previous_failures(previous_state) + 1
        last_success = isoformat_z(collected_at) if ok else previous_success
        next_due = add_seconds(collected_at, interval_seconds if ok else self._backoff_seconds(failures))
        poll_id = self.storage.record_poll(
            PollRecord(
                source=source,
                attempted_at_utc=isoformat_z(attempted_at) or "",
                collected_at_utc=isoformat_z(collected_at),
                foli_server_time_utc=foli_server_time_utc,
                status=status,
                ok=ok,
                http_status=http_status,
                row_count=row_count,
                latency_ms=latency_ms,
                error_text=error_text,
                gap_seconds_since_previous_success=gap_seconds,
            )
        )
        self.storage.upsert_state(
            source=source,
            last_success_at_utc=last_success,
            last_attempted_at_utc=isoformat_z(attempted_at) or "",
            last_status=status,
            consecutive_failures=failures,
            next_due_at_utc=next_due,
        )
        self.local_next_due.pop(source, None)
        self.local_failures[source] = failures
        return poll_id

    def _record_failure(
        self,
        *,
        source: str,
        attempted_at: datetime,
        status: str,
        error_text: str,
        interval_seconds: int,
        previous_state: dict[str, object] | None,
    ) -> None:
        try:
            self._record_poll_and_state(
                source=source,
                attempted_at=attempted_at,
                collected_at=utc_now(),
                foli_server_time_utc=None,
                status=status,
                ok=False,
                http_status=None,
                row_count=0,
                latency_ms=None,
                error_text=error_text,
                interval_seconds=interval_seconds,
                previous_state=previous_state,
            )
            self.storage.commit()
        except Exception:
            self.storage.rollback()
            failures = self.local_failures.get(source, _previous_failures(previous_state)) + 1
            self.local_failures[source] = failures
            self.local_next_due[source] = utc_now() + self._backoff_delta(failures)
            self.logger.exception("failed to record %s failure in database", source)

    def _run_job(self, job: Job) -> None:
        try:
            job.run()
        except Exception:
            failures = self.local_failures.get(job.source, 0) + 1
            self.local_failures[job.source] = failures
            self.local_next_due[job.source] = utc_now() + self._backoff_delta(failures)
            self.logger.exception("%s job crashed; continuing collector loop", job.source)

    def _is_due(self, job: Job, now: datetime) -> bool:
        local_due = self.local_next_due.get(job.source)
        if local_due and local_due > now:
            return False
        state = self.storage.get_state(job.source)
        if state is None or not state.get("next_due_at_utc"):
            return True
        next_due = parse_utc(str(state["next_due_at_utc"]))
        return next_due is None or next_due <= now

    def _sleep_until_next_due(self) -> None:
        time.sleep(1)

    def _backoff_seconds(self, failures: int) -> int:
        return min(
            self.config.backoff_max_seconds,
            self.config.backoff_base_seconds * max(1, 2 ** (failures - 1)),
        )

    def _backoff_delta(self, failures: int):
        from datetime import timedelta

        return timedelta(seconds=self._backoff_seconds(failures))

    def _install_signal_handlers(self) -> None:
        def stop(_signum, _frame) -> None:
            self.should_stop = True

        for signal_name in ("SIGINT", "SIGTERM"):
            signum = getattr(signal, signal_name, None)
            if signum is not None:
                signal.signal(signum, stop)


def _previous_failures(previous_state: dict[str, object] | None) -> int:
    if not previous_state:
        return 0
    try:
        return int(previous_state.get("consecutive_failures") or 0)
    except (TypeError, ValueError):
        return 0
