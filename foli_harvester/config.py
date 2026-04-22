from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    dotenv_path = _find_dotenv_path()
    if dotenv_path is not None:
        load_dotenv(dotenv_path=dotenv_path)
        return
    load_dotenv()


def _find_dotenv_path() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    candidates.append(Path.cwd() / ".env")

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


@dataclass(frozen=True)
class Config:
    database_url: str
    auth_token: str | None
    foli_base_url: str
    foli_user_agent: str
    poll_vm_seconds: int
    poll_alerts_seconds: int
    gtfs_archive_interval_hours: int
    data_dir: Path
    collector_instance_id: str
    request_timeout_seconds: int
    lock_ttl_seconds: int
    lock_heartbeat_seconds: int
    backoff_base_seconds: int
    backoff_max_seconds: int
    healthcheck_vm_max_age_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        default_instance_id = f"{platform.node() or 'host'}-{os.getpid()}"
        return cls(
            database_url=os.getenv("TURSO_DATABASE_URL", "file:data/foli.db"),
            auth_token=os.getenv("TURSO_AUTH_TOKEN") or None,
            foli_base_url=os.getenv("FOLI_BASE_URL", "http://data.foli.fi").rstrip("/"),
            foli_user_agent=os.getenv(
                "FOLI_USER_AGENT",
                "foli-data-collector/0.1.0 (local; no-public)",
            ),
            poll_vm_seconds=_int_env("POLL_VM_SECONDS", 30),
            poll_alerts_seconds=_int_env("POLL_ALERTS_SECONDS", 300),
            gtfs_archive_interval_hours=_int_env("GTFS_ARCHIVE_INTERVAL_HOURS", 168),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            collector_instance_id=os.getenv("COLLECTOR_INSTANCE_ID", default_instance_id),
            request_timeout_seconds=_int_env("REQUEST_TIMEOUT_SECONDS", 20),
            lock_ttl_seconds=_int_env("LOCK_TTL_SECONDS", 90),
            lock_heartbeat_seconds=_int_env("LOCK_HEARTBEAT_SECONDS", 30),
            backoff_base_seconds=_int_env("BACKOFF_BASE_SECONDS", 15),
            backoff_max_seconds=_int_env("BACKOFF_MAX_SECONDS", 300),
            healthcheck_vm_max_age_seconds=_int_env("HEALTHCHECK_VM_MAX_AGE_SECONDS", 300),
        )

    @property
    def gtfs_dir(self) -> Path:
        return self.data_dir / "gtfs"

    @property
    def gtfs_interval_seconds(self) -> int:
        return self.gtfs_archive_interval_hours * 60 * 60
