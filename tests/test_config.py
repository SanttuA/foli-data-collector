import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from foli_harvester.config import _find_dotenv_path


class ConfigTests(unittest.TestCase):
    def test_find_dotenv_uses_current_directory_for_normal_python(self):
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dotenv_path = tmp_path / ".env"
            dotenv_path.write_text("TURSO_DATABASE_URL=file:data/test.db\n", encoding="utf-8")
            os.chdir(tmp_path)
            try:
                self.assertEqual(_find_dotenv_path(), dotenv_path)
            finally:
                os.chdir(previous_cwd)

    def test_find_dotenv_prefers_exe_directory_when_frozen(self):
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            exe_dir = tmp_path / "portable"
            cwd_dir = tmp_path / "cwd"
            exe_dir.mkdir()
            cwd_dir.mkdir()
            exe_dotenv = exe_dir / ".env"
            cwd_dotenv = cwd_dir / ".env"
            exe_dotenv.write_text("TURSO_DATABASE_URL=file:data/exe.db\n", encoding="utf-8")
            cwd_dotenv.write_text("TURSO_DATABASE_URL=file:data/cwd.db\n", encoding="utf-8")
            os.chdir(cwd_dir)
            try:
                with (
                    patch.object(sys, "frozen", True, create=True),
                    patch.object(sys, "executable", str(exe_dir / "foli-harvester.exe")),
                ):
                    self.assertEqual(_find_dotenv_path(), exe_dotenv)
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
