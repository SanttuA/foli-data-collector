import unittest
from datetime import UTC, datetime
from email.utils import format_datetime

from foli_harvester.gtfs import next_gtfs_filename, sha256_bytes, write_gtfs_archive


class GtfsTests(unittest.TestCase):
    def test_next_gtfs_filename_adds_suffix_for_same_day_downloads(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            from pathlib import Path

            tmp_path = Path(tmp)
            (tmp_path / "gtfs_2026-04-22.zip").write_bytes(b"first")
            (tmp_path / "gtfs_2026-04-22_2.zip").write_bytes(b"second")

            self.assertEqual(
                next_gtfs_filename(tmp_path, "2026-04-22"),
                "gtfs_2026-04-22_3.zip",
            )

    def test_write_gtfs_archive_persists_metadata(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            from pathlib import Path

            tmp_path = Path(tmp)
            modified = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
            body = b"gtfs bytes"

            metadata = write_gtfs_archive(
                body=body,
                headers={"ETag": '"abc"', "Last-Modified": format_datetime(modified, usegmt=True)},
                gtfs_dir=tmp_path,
                source_url="http://data.foli.fi/gtfs/gtfs.zip",
            )

            self.assertEqual((tmp_path / metadata.stored_filename).read_bytes(), body)
            self.assertEqual(metadata.sha256, sha256_bytes(body))
            self.assertEqual(metadata.byte_size, len(body))
            self.assertEqual(metadata.etag, '"abc"')
            self.assertEqual(metadata.last_modified, "2026-04-20T09:00:00Z")


if __name__ == "__main__":
    unittest.main()
