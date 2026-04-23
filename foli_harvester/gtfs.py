from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .timeutils import http_date_to_iso, isoformat_z, utc_now


@dataclass(frozen=True)
class GtfsMetadata:
    downloaded_at_utc: str
    download_service_date: str
    stored_filename: str
    local_path: str
    sha256: str
    byte_size: int
    etag: str | None
    last_modified: str | None
    source_url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "downloaded_at_utc": self.downloaded_at_utc,
            "download_service_date": self.download_service_date,
            "stored_filename": self.stored_filename,
            "local_path": self.local_path,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "source_url": self.source_url,
        }


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def next_gtfs_filename(gtfs_dir: Path, service_date: str) -> str:
    base = f"gtfs_{service_date}.zip"
    if not (gtfs_dir / base).exists():
        return base
    suffix = 2
    while True:
        candidate = f"gtfs_{service_date}_{suffix}.zip"
        if not (gtfs_dir / candidate).exists():
            return candidate
        suffix += 1


def write_gtfs_archive(
    *,
    body: bytes,
    headers: dict[str, str],
    gtfs_dir: Path,
    source_url: str,
) -> GtfsMetadata:
    now = utc_now()
    downloaded_at = isoformat_z(now) or ""
    service_date = now.date().isoformat()
    gtfs_dir.mkdir(parents=True, exist_ok=True)
    filename = next_gtfs_filename(gtfs_dir, service_date)
    target = gtfs_dir / filename
    tmp_target = target.with_suffix(target.suffix + ".tmp")
    tmp_target.write_bytes(body)
    tmp_target.replace(target)
    return GtfsMetadata(
        downloaded_at_utc=downloaded_at,
        download_service_date=service_date,
        stored_filename=filename,
        local_path=str(target),
        sha256=sha256_bytes(body),
        byte_size=len(body),
        etag=headers.get("ETag") or headers.get("etag"),
        last_modified=http_date_to_iso(
            headers.get("Last-Modified") or headers.get("last-modified")
        ),
        source_url=source_url,
    )
