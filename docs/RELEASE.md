# Versioning And Release Checklist

This checklist covers the Python package and the lightweight macOS application.
A release does not imply affiliation with or support from Zscaler. See
[../DISCLAIMER.md](../DISCLAIMER.md).

## Version Policy

Use semantic versioning:

- `PATCH` for backward-compatible fixes and documentation corrections;
- `MINOR` for backward-compatible features or newly enabled API coverage;
- `MAJOR` for incompatible CLI, backup-schema, assurance-schema, or restore
  behavior changes.

The application version has one source of truth:
`zpa_backup_restore/version.py`. `pyproject.toml` reads it dynamically, and
`build_macos_app.py` uses it for both macOS bundle version fields. Backup,
simulation-assurance, execution-journal, catalog, and ledger schema versions
are independent compatibility contracts and must not be changed merely because
the application version changes.

## Version-Bump Procedure

1. Choose the semantic version from the user-visible and compatibility impact.
2. Update `zpa_backup_restore/version.py`.
3. Update the version assertion in `test_v2_architecture.py`.
4. Update the package/application release shown in `README.md`.
5. Move relevant entries from `Unreleased` into a dated section in
   [../CHANGELOG.md](../CHANGELOG.md).
6. Search for version declarations and stale release wording:

   ```sh
   rg -n '__version__|Package/application release|## [0-9]+\.[0-9]+\.[0-9]+' \
     README.md CHANGELOG.md docs zpa_backup_restore test_*.py build_macos_app.py
   ```

7. Confirm that backup and other persisted-artifact schema versions changed
   only when a migration and backward-compatibility plan requires it.

## Release Validation

Run from the repository root:

```sh
python3 -m compileall -q zpa_backup_restore *.py
python3 -m unittest discover -v
python3 -m zpa_backup_restore --help
python3 -m zpa_backup_restore coverage
python3 -m build
python3 build_macos_app.py
plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"
sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"
git diff --check
```

Then verify:

- the test suite reports no failures;
- `dist/` contains both source/wheel package artifacts and the `.app`;
- the wheel contains `zpa_backup_restore`, all operation packages, and the
  legacy compatibility modules;
- neither package archive contains `__pycache__`, `.pyc`, or `.pyo` files;
- the source archive contains the project metadata and user-facing
  documentation selected by the packaging configuration;
- package metadata, `zpa_backup_restore.__version__`, and both macOS bundle
  version fields agree;
- the app launches with a native Python/Tkinter runtime on the supported macOS
  architecture;
- generated backups, state, logs, reports, `.env`, and app bundles remain
  ignored by Git; and
- the official ZPA sitemap count and the dated coverage audit are still current.

If `python3 -m build` is unavailable, install the development-only `build`
package in an isolated environment; it is not a runtime dependency. Static type
checking is currently not configured and must be recorded as skipped.

## Lab Acceptance

Before a release that changes API behavior or restore planning:

1. Complete the lab-tenant rehearsal in
   [OPERATIONS.md](OPERATIONS.md#production-rehearsal-in-a-lab-tenant).
2. Retain the desired snapshot, reviewed destination snapshot, diff,
   simulation JSON/HTML, execution journal, restore result, pre/post snapshots,
   residual report, HTTP audit log, and run-ledger events.
3. Record any endpoint behavior that differs from fixtures or official
   documentation.
4. Do not enable a catalog-only or excluded operation based only on unit tests.

## Publish And Rollback

1. Review the final diff and ensure `main` is releasable.
2. Create an annotated `vMAJOR.MINOR.PATCH` tag on the validated commit.
3. Publish the wheel, source archive, macOS app archive, checksums, and release
   notes through the project’s approved distribution channel.
4. State the supported authentication modes, backup schema, coverage boundary,
   known catalog-only operations, and whether live lab validation was completed.
5. Preserve the previous release artifacts and checksums.

If a release is unsafe, withdraw the affected artifacts, mark the release as
superseded, restore the previous release through the normal distribution
channel, and publish a corrective version. Do not move or reuse an existing
release tag.
