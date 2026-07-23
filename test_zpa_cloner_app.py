import unittest
from pathlib import Path

from zpa_cloner_app import (
    ACTION_TOOLTIPS,
    ARTIFACT_TOOLTIPS,
    COMPACT_GRID_COLUMNS,
    CREDENTIAL_FIELDS,
    CREDENTIAL_TOOLTIPS,
    DISCLAIMER_TEXT,
    LEFT_PANEL_TABS,
    SAFEGUARD_TOOLTIPS,
    TAB_TOOLTIPS,
    auth_mode_for_profile,
    build_encryption_args,
    build_dr_runbook_args,
    build_policy_args,
    build_restore_selection_args,
    compact_grid_position,
    credential_env_name,
    default_work_dir,
    extract_artifact,
    missing_env,
    parse_env_lines,
    parse_restore_selectors,
    policy_display_name,
    resource_display_name,
    required_env_for_profile,
    running_from_macos_bundle,
    status_from_line,
)
from zpa_resources import POLICY_TYPES


class ZpaClonerAppHelperTests(unittest.TestCase):
    def test_left_panel_uses_six_focused_tabs(self) -> None:
        self.assertEqual(
            LEFT_PANEL_TABS,
            ("Workflow", "Tenants", "Options", "Scope", "Artifacts", "Status"),
        )

    def test_contextual_tooltips_cover_navigation_actions_and_technical_fields(self) -> None:
        expected_actions = {
            "Backup Source",
            "Backup Destination",
            "Compare Source to Destination",
            "Choose Desired Backup",
            "Build Restore Plan",
            "Validate",
            "Preflight",
            "Simulate",
            "Restore",
            "Snapshots",
            "Latest Inventory",
            "Audit Summary",
            "Verify Ledger",
            "Report",
            "DR Runbook",
            "Coverage",
        }
        expected_safeguards = {
            "Strict manifest",
            "Allow deletes",
            "Allow high-impact",
            "Allow endpoint-error backups",
            "Bypass preflight block",
        }
        expected_artifacts = {
            "Desired backup",
            "Destination backup",
            "Restore diff",
            "Report",
            "Reviewed simulation",
            "Restore result",
            "Audit log",
            "DR runbook",
            "DR checklist",
        }

        self.assertEqual(set(TAB_TOOLTIPS), set(LEFT_PANEL_TABS))
        self.assertEqual(set(ACTION_TOOLTIPS), expected_actions)
        self.assertEqual(set(SAFEGUARD_TOOLTIPS), expected_safeguards)
        self.assertEqual(set(CREDENTIAL_TOOLTIPS), {field[0] for field in CREDENTIAL_FIELDS})
        self.assertEqual(set(ARTIFACT_TOOLTIPS), expected_artifacts)
        all_text = [
            *TAB_TOOLTIPS.values(),
            *ACTION_TOOLTIPS.values(),
            *SAFEGUARD_TOOLTIPS.values(),
            *CREDENTIAL_TOOLTIPS.values(),
            *ARTIFACT_TOOLTIPS.values(),
        ]
        self.assertTrue(all(text.endswith(".") and len(text) >= 30 for text in all_text))
        self.assertIn("Destination tenant", ACTION_TOOLTIPS["Restore"])
        self.assertIn("weakens", SAFEGUARD_TOOLTIPS["Bypass preflight block"])

    def test_compact_grid_keeps_ten_policy_types_to_five_rows(self) -> None:
        positions = [
            compact_grid_position(index)
            for index in range(len(POLICY_TYPES))
        ]

        self.assertEqual(COMPACT_GRID_COLUMNS, 2)
        self.assertEqual(max(row for row, _column in positions), 4)
        self.assertEqual({column for _row, column in positions}, {0, 1})

    def test_compact_grid_rejects_invalid_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            compact_grid_position(-1)
        with self.assertRaises(ValueError):
            compact_grid_position(0, columns=0)

    def test_policy_display_name_removes_repeated_policy_suffix(self) -> None:
        self.assertEqual(
            policy_display_name("CLIENTLESS_SESSION_PROTECTION_POLICY"),
            "Clientless Session Protection",
        )

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

    def test_build_encryption_args_adds_global_flag_when_enabled(self) -> None:
        self.assertEqual(build_encryption_args(True), ["--encrypt-backups"])
        self.assertEqual(build_encryption_args(False), [])

    def test_build_dr_runbook_args_uses_selected_backup_and_encryption_context(self) -> None:
        self.assertEqual(
            build_dr_runbook_args(
                "backups/recovery.json.enc",
                encrypt_backups=True,
            ),
            [
                "--encrypt-backups",
                "dr",
                "generate",
                "--source-backup",
                "backups/recovery.json.enc",
            ],
        )
        with self.assertRaises(ValueError):
            build_dr_runbook_args("", encrypt_backups=False)

    def test_restore_selection_args_support_objects_resources_and_explicit_options(self) -> None:
        self.assertEqual(
            build_restore_selection_args(
                "policy_rules/ACCESS_POLICY:accesspolicy13, servers/servera",
                ["server_groups"],
                include_dependencies=True,
                restore_policy_order=True,
            ),
            [
                "--select",
                "policy_rules/ACCESS_POLICY:accesspolicy13",
                "--select",
                "servers/servera",
                "--select-resource",
                "server_groups",
                "--include-dependencies",
                "--restore-policy-order",
            ],
        )

    def test_restore_selection_options_require_a_scope(self) -> None:
        with self.assertRaises(ValueError):
            build_restore_selection_args(
                "",
                [],
                include_dependencies=True,
                restore_policy_order=False,
            )

    def test_restore_selector_parser_accepts_commas_and_lines(self) -> None:
        self.assertEqual(
            parse_restore_selectors("servers/a,\nserver_groups/b"),
            ["servers/a", "server_groups/b"],
        )

    def test_resource_display_name_is_operator_friendly(self) -> None:
        self.assertEqual(
            resource_display_name("application_segments"),
            "Application Segments",
        )

    def test_extract_artifacts_from_cli_output(self) -> None:
        self.assertEqual(extract_artifact("audit log: logs/run.log"), ("audit_log", "logs/run.log"))
        self.assertEqual(extract_artifact("source backup: backups/run-source.json"), ("source_backup", "backups/run-source.json"))
        self.assertEqual(extract_artifact("report written: backups/run.html"), ("report", "backups/run.html"))
        self.assertEqual(extract_artifact("restore result: backups/result.json"), ("apply_result", "backups/result.json"))
        self.assertEqual(extract_artifact("simulation: backups/simulation.json"), ("simulation", "backups/simulation.json"))
        self.assertEqual(extract_artifact("dr runbook: backups/dr.json"), ("dr_runbook", "backups/dr.json"))
        self.assertEqual(extract_artifact("dr checklist: backups/dr.html"), ("dr_report", "backups/dr.html"))

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
        self.assertEqual(
            status_from_line("simulation summary: planned=1 skipped=2 blocked=0 deferred=1 unresolved=0"),
            "simulation summary: planned=1 skipped=2 blocked=0 deferred=1 unresolved=0",
        )
        self.assertEqual(
            status_from_line("restore scope: 1 selected object(s)"),
            "restore scope: 1 selected object(s)",
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
