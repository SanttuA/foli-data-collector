import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from foli_harvester.db import connect_database
from foli_harvester.collector import Collector
from foli_harvester.config import Config
from foli_harvester.lock import CollectorLock
from foli_harvester.storage import PollRecord, Storage
from foli_harvester.timeutils import add_seconds, isoformat_z, utc_now


def make_storage(tmp_path):
    conn = connect_database(f"file:{tmp_path / 'test.db'}")
    storage = Storage(conn)
    storage.init_schema()
    return storage


class StorageAndLockTests(unittest.TestCase):
    def test_init_db_and_insert_core_rows(self):
        with TemporaryDirectory() as tmp:
            storage = make_storage(Path(tmp))
            now = utc_now()
            poll_id = storage.record_poll(
                PollRecord(
                    source="siri_vm",
                    attempted_at_utc=isoformat_z(now),
                    collected_at_utc=isoformat_z(now),
                    foli_server_time_utc=None,
                    status="OK",
                    ok=True,
                    http_status=200,
                    row_count=1,
                    latency_ms=10,
                    error_text=None,
                    gap_seconds_since_previous_success=None,
                )
            )
            storage.insert_vehicle_observations(
                poll_id,
                [
                    {
                        "vehicle_id": "550011",
                        "line_ref": "14",
                        "direction_ref": "1",
                        "origin_aimed_departure_unix": 1433258100,
                        "trip_match_key": "14|1|1433258100",
                        "is_gtfs_matchable": True,
                    }
                ],
            )
            storage.upsert_state(
                source="siri_vm",
                last_success_at_utc=isoformat_z(now),
                last_attempted_at_utc=isoformat_z(now),
                last_status="OK",
                consecutive_failures=0,
                next_due_at_utc=add_seconds(now, 30),
            )
            storage.commit()

            state = storage.get_state("siri_vm")
            self.assertGreater(poll_id, 0)
            self.assertEqual(state["last_status"], "OK")

    def test_collector_lock_refuses_live_owner_and_takes_expired_lock(self):
        with TemporaryDirectory() as tmp:
            storage = make_storage(Path(tmp))
            first = CollectorLock(storage, owner_id="first", ttl_seconds=30)
            second = CollectorLock(storage, owner_id="second", ttl_seconds=30)

            self.assertIs(first.acquire(), True)
            self.assertIs(second.acquire(), False)

            expired = isoformat_z(utc_now() - timedelta(seconds=1))
            storage.conn.execute(
                "UPDATE collector_lock SET expires_at_utc = ? WHERE lock_name = ?",
                (expired, first.lock_name),
            )
            storage.commit()

            self.assertIs(second.acquire(), True)
            self.assertEqual(storage.get_lock(first.lock_name)["owner_id"], "second")

    def test_insert_alert_and_gtfs_metadata(self):
        with TemporaryDirectory() as tmp:
            storage = make_storage(Path(tmp))
            now = utc_now()
            poll_id = storage.record_poll(
                PollRecord(
                    source="siri_alerts",
                    attempted_at_utc=isoformat_z(now),
                    collected_at_utc=isoformat_z(now),
                    foli_server_time_utc=None,
                    status="OK",
                    ok=True,
                    http_status=200,
                    row_count=1,
                    latency_ms=20,
                    error_text=None,
                    gap_seconds_since_previous_success=None,
                )
            )
            storage.insert_service_alerts(
                poll_id,
                [
                    {
                        "alert_type": "message",
                        "source_alert_id": "abc",
                        "line_ref": "14",
                        "message": "test",
                        "affected_routes_json": '["14"]',
                        "affected_stops_json": "[]",
                        "categories_json": "[]",
                    }
                ],
            )
            archive_id = storage.insert_gtfs_archive(
                {
                    "downloaded_at_utc": isoformat_z(now),
                    "download_service_date": now.date().isoformat(),
                    "stored_filename": "gtfs_2026-04-22.zip",
                    "local_path": "data/gtfs/gtfs_2026-04-22.zip",
                    "sha256": "a" * 64,
                    "byte_size": 10,
                    "etag": '"etag"',
                    "last_modified": "2026-04-20T09:00:00Z",
                    "source_url": "http://data.foli.fi/gtfs/gtfs.zip",
                }
            )
            storage.commit()

            self.assertEqual(storage.find_gtfs_by_sha256("a" * 64)["id"], archive_id)

    def test_collector_backoff_is_capped(self):
        with TemporaryDirectory() as tmp:
            config = Config(
                database_url=f"file:{Path(tmp) / 'test.db'}",
                auth_token=None,
                foli_base_url="http://example.invalid",
                foli_user_agent="test",
                poll_vm_seconds=30,
                poll_alerts_seconds=300,
                gtfs_archive_interval_hours=168,
                data_dir=Path(tmp) / "data",
                collector_instance_id="test",
                request_timeout_seconds=1,
                lock_ttl_seconds=90,
                lock_heartbeat_seconds=30,
                backoff_base_seconds=15,
                backoff_max_seconds=60,
                healthcheck_vm_max_age_seconds=300,
            )
            collector = Collector(config)
            self.assertEqual(collector._backoff_seconds(1), 15)
            self.assertEqual(collector._backoff_seconds(2), 30)
            self.assertEqual(collector._backoff_seconds(3), 60)
            self.assertEqual(collector._backoff_seconds(10), 60)


if __name__ == "__main__":
    unittest.main()
