import unittest
from pathlib import Path

from zpa_cloner_app import (
    DISCLAIMER_TEXT,
    auth_mode_for_profile,
    build_policy_args,
    credential_env_name,
    default_work_dir,
    extract_artifact,
    missing_env,
    parse_env_lines,
    required_env_for_profile,
    running_from_macos_bundle,
    status_from_line,
)
from zpa_resources import POLICY_TYPES


class ZpaClonerAppHelperTests(unittest.TestCase):
    def test_disclaimer_text_is_visible_and_explicit(self) -> None:
        self.assertIn("Not affiliated", DISCLAIMER_TEXT)
        self.assertIn("Zscaler", DISCLAIMER_TEXT)
        self.assertIn("without warranty", DISCLAIMER_TEXT)

    def test_build_policy_args_defaults_to_all_policy_rule_types(self) -> None:
        expected = []
        for policy_type in POLICY_TYPES:
            expected.extend(["--policy-type", policy_type])

        self.assertEqual(build_policy_args(""), expected)

    def test_build_policy_args_accepts_commas_and_spaces(self) -> None:
        self.assertEqual(
            build_policy_args("ACCESS_POLICY, TIMEOUT_POLICY INSPECTION_POLICY"),
            [
                "--policy-type",
                "ACCESS_POLICY",
                "--policy-type",
                "TIMEOUT_POLICY",
                "--policy-type",
                "INSPECTION_POLICY",
            ],
        )

    def test_extract_artifacts_from_cli_output(self) -> None:
        self.assertEqual(extract_artifact("audit log: logs/run.log"), ("audit_log", "logs/run.log"))
        self.assertEqual(extract_artifact("source backup: backups/run-source.json"), ("source_backup", "backups/run-source.json"))
        self.assertEqual(extract_artifact("report written: backups/run.html"), ("report", "backups/run.html"))
        self.assertEqual(extract_artifact("restore result: backups/result.json"), ("apply_result", "backups/result.json"))

    def test_status_from_backup_line(self) -> None:
        self.assertEqual(status_from_line("backup target: policy rules"), "Backing up target: policy rules")

    def test_status_from_api_progress_line(self) -> None:
        self.assertEqual(
            status_from_line("api: GET /mgmtconfig/v1/admin/customers/123/application?page=1&pagesize=500 start"),
            "GET /mgmtconfig/v1/admin/customers/123/application?page=1&pagesize=500 start",
        )

    def test_status_from_restore_progress_lines(self) -> None:
        self.assertEqual(status_from_line("restore plan: mode=DRY-RUN"), "restore plan: mode=DRY-RUN")
        self.assertEqual(
            status_from_line("UPDATE  application_segments   DRY-RUN lab-app-web"),
            "Dry-run Update application_segments: lab-app-web",
        )
        self.assertEqual(
            status_from_line("UPDATE  application_segments   OK      lab-app-web"),
            "Update application_segments: lab-app-web (OK)",
        )
        self.assertEqual(
            status_from_line("restore summary: ok=1 dry-run=0 skipped=0 errors=0"),
            "restore summary: ok=1 dry-run=0 skipped=0 errors=0",
        )

    def test_parse_env_lines_handles_quoted_secret_without_printing_it(self) -> None:
        values = parse_env_lines(
            [
                'export ZPA_SOURCE_CLIENT_SECRET="dummy-secret-with-quote\'"',
                "ZPA_SOURCE_CUSTOMER_ID=1234567890",
                "# ignored",
            ]
        )

        self.assertEqual(values["ZPA_SOURCE_CUSTOMER_ID"], "1234567890")
        self.assertEqual(values["ZPA_SOURCE_CLIENT_SECRET"], "dummy-secret-with-quote'")

    def test_bundle_paths_use_documents_work_dir(self) -> None:
        resources = Path("/Applications/ZPA-Backup and Restore.app/Contents/Resources")

        self.assertTrue(running_from_macos_bundle(resources))
        self.assertEqual(default_work_dir(resources), Path.home() / "Documents" / "ZPA-Backup and Restore")

    def test_non_bundle_paths_use_project_dir(self) -> None:
        project = Path("/tmp/zpa")

        self.assertFalse(running_from_macos_bundle(project))
        self.assertEqual(default_work_dir(project), project)

    def test_credential_env_name_uses_zpa_prefixes(self) -> None:
        self.assertEqual(credential_env_name("source", "CLIENT_ID"), "ZPA_SOURCE_CLIENT_ID")
        self.assertEqual(credential_env_name("target", "CLIENT_SECRET"), "ZPA_TARGET_CLIENT_SECRET")

    def test_missing_env_accepts_explicit_values(self) -> None:
        values = {"ZPA_SOURCE_CLIENT_ID": "id"}

        self.assertEqual(missing_env(["ZPA_SOURCE_CLIENT_ID", "ZPA_SOURCE_CLIENT_SECRET"], values), ["ZPA_SOURCE_CLIENT_SECRET"])

    def test_legacy_profile_does_not_require_zidentity(self) -> None:
        values = {
            "ZPA_SOURCE_AUTH_MODE": "legacy",
            "ZPA_SOURCE_CLIENT_ID": "id",
            "ZPA_SOURCE_CLIENT_SECRET": "secret",
            "ZPA_SOURCE_CUSTOMER_ID": "customer",
        }

        self.assertEqual(auth_mode_for_profile("source", values), "legacy")
        self.assertEqual(missing_env(required_env_for_profile("source", values), values), [])

    def test_oneapi_profile_requires_zidentity(self) -> None:
        values = {
            "ZPA_SOURCE_AUTH_MODE": "oneapi",
            "ZPA_SOURCE_CLIENT_ID": "id",
            "ZPA_SOURCE_CLIENT_SECRET": "secret",
            "ZPA_SOURCE_CUSTOMER_ID": "customer",
        }

        self.assertEqual(auth_mode_for_profile("source", values), "oneapi")
        self.assertEqual(missing_env(required_env_for_profile("source", values), values), ["ZPA_SOURCE_ZIDENTITY_BASE_URL"])


if __name__ == "__main__":
    unittest.main()
