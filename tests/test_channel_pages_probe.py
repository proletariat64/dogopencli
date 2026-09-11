"""Offline checks for channel probe export placement."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "channel_pages_probe",
    Path(__file__).resolve().parent / "integration/channel_pages_probe.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ChannelProbeExportTests(unittest.TestCase):
    def test_explicit_root_is_private_and_export_is_nested(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "persistent" / "channel"
            export_dir = MODULE.make_export_dir(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(export_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(export_dir.parent, root)

    def test_explicit_root_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "under tmp"):
            MODULE.make_export_dir(MODULE.REPO_ROOT / "exports")

    def test_repo_tmp_root_is_allowed(self):
        MODULE.REPO_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=MODULE.REPO_TMP_ROOT) as temp:
            export_dir = MODULE.make_export_dir(temp)
            self.assertEqual(export_dir.parent, Path(temp))
            export_dir.rmdir()

    def test_default_root_remains_system_temp(self):
        export_dir = MODULE.make_export_dir()
        try:
            self.assertEqual(export_dir.parent, Path(tempfile.gettempdir()))
            self.assertEqual(export_dir.stat().st_mode & 0o777, 0o700)
        finally:
            export_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
