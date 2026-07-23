import subprocess
import sys
import unittest

import build_macos_app
import zpa_cloner
import zpa_resources
from zpa_backup_restore import __version__
from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.resources import RESOURCES, RESOURCE_SPECS


class V2ArchitectureTests(unittest.TestCase):
    def test_release_versions_are_aligned(self) -> None:
        self.assertEqual(__version__, "2.0.0")
        self.assertEqual(build_macos_app.VERSION, __version__)

    def test_resource_specs_preserve_the_legacy_catalog(self) -> None:
        self.assertIs(zpa_resources.RESOURCES, RESOURCES)
        self.assertEqual(list(RESOURCE_SPECS), list(RESOURCES))
        for key, spec in RESOURCE_SPECS.items():
            self.assertEqual(spec.as_legacy_dict(), RESOURCES[key])

    def test_resource_actions_follow_write_safety(self) -> None:
        self.assertEqual(RESOURCE_SPECS["application_segments"].detail_strategy, "list")
        self.assertIn("delete", RESOURCE_SPECS["application_segments"].actions)
        self.assertEqual(RESOURCE_SPECS["posture_profiles"].actions, ("list", "get"))
        self.assertTrue(RESOURCE_SPECS["microtenants"].high_impact)

    def test_legacy_cloner_exports_the_v2_core(self) -> None:
        self.assertIs(zpa_cloner.compute_diff, compute_diff)

    def test_package_module_is_a_cli_entry_point(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "zpa_backup_restore", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("backup", result.stdout)
        self.assertIn("restore", result.stdout)


if __name__ == "__main__":
    unittest.main()
