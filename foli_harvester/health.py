from __future__ import annotations

from pathlib import Path

from .config import Config
from .db import connect_database
from .lock import LOCK_NAME
from .storage import Storage
from .timeutils import parse_utc, utc_now


def run_healthcheck(config: Config) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        conn = connect_database(config.database_url, config.auth_token)
        storage = Storage(conn)
        conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        return False, [f"database unreachable: {exc}"]

    try:
        _check_writable(config.gtfs_dir)
    except Exception as exc:
        errors.append(f"GTFS directory is not writable: {exc}")

    try:
        lock = storage.get_lock(LOCK_NAME)
        if lock:
            expires_at = parse_utc(lock.get("expires_at_utc"))
            if expires_at is None or expires_at <= utc_now():
                errors.append("collector lock exists but is expired")
    except Exception as exc:
        errors.append(f"collector lock check failed: {exc}")

    try:
        state = storage.get_state("siri_vm")
        if not state or not state.get("last_success_at_utc"):
            errors.append("no successful SIRI VM poll recorded")
        else:
            last_success = parse_utc(str(state["last_success_at_utc"]))
            if last_success is None:
                errors.append("latest SIRI VM success timestamp is invalid")
            else:
                age = (utc_now() - last_success).total_seconds()
                if age > config.healthcheck_vm_max_age_seconds:
                    errors.append(
                        "latest SIRI VM success is too old: "
                        f"{int(age)}s > {config.healthcheck_vm_max_age_seconds}s"
                    )
    except Exception as exc:
        errors.append(f"SIRI VM state check failed: {exc}")

    if hasattr(conn, "close"):
        conn.close()
    return not errors, errors


def _check_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".healthcheck.tmp"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()

