from __future__ import annotations

from dataclasses import dataclass

from .storage import Storage
from .timeutils import add_seconds, isoformat_z, parse_utc, utc_now

LOCK_NAME = "foli_harvester"


@dataclass
class CollectorLock:
    storage: Storage
    owner_id: str
    ttl_seconds: int
    lock_name: str = LOCK_NAME

    def acquire(self) -> bool:
        now = utc_now()
        now_iso = isoformat_z(now) or ""
        expires_at = add_seconds(now, self.ttl_seconds)
        existing = self.storage.get_lock(self.lock_name)

        if existing is None:
            self.storage.insert_lock(
                lock_name=self.lock_name,
                owner_id=self.owner_id,
                acquired_at_utc=now_iso,
                heartbeat_at_utc=now_iso,
                expires_at_utc=expires_at,
            )
            self.storage.commit()
            return True

        if existing["owner_id"] == self.owner_id or _is_expired(existing["expires_at_utc"]):
            self.storage.update_lock(
                lock_name=self.lock_name,
                owner_id=self.owner_id,
                acquired_at_utc=now_iso,
                heartbeat_at_utc=now_iso,
                expires_at_utc=expires_at,
            )
            self.storage.commit()
            return True

        return False

    def renew(self) -> bool:
        now = utc_now()
        self.storage.update_lock(
            lock_name=self.lock_name,
            owner_id=self.owner_id,
            heartbeat_at_utc=isoformat_z(now) or "",
            expires_at_utc=add_seconds(now, self.ttl_seconds),
        )
        self.storage.commit()
        current = self.storage.get_lock(self.lock_name)
        return bool(current and current["owner_id"] == self.owner_id)

    def release(self) -> None:
        self.storage.delete_lock(lock_name=self.lock_name, owner_id=self.owner_id)
        self.storage.commit()


def _is_expired(expires_at_utc: str | None) -> bool:
    expires_at = parse_utc(expires_at_utc)
    return expires_at is None or expires_at <= utc_now()
