#!/usr/bin/env python3
"""Compatibility facade for the package-based v2 implementation.

New commands should use ``python3 -m zpa_backup_restore``. Existing imports and
``python3 zpa_cloner.py`` remain supported during the v2 migration.
"""

from zpa_backup_restore.cli import *  # noqa: F401,F403
from zpa_backup_restore.core.backup import *  # noqa: F401,F403
from zpa_backup_restore.core.catalog import *  # noqa: F401,F403
from zpa_backup_restore.core.diff import *  # noqa: F401,F403
from zpa_backup_restore.core.integrity import *  # noqa: F401,F403
from zpa_backup_restore.core.mapping import *  # noqa: F401,F403
from zpa_backup_restore.core.restore import *  # noqa: F401,F403
from zpa_backup_restore.core.simulation import *  # noqa: F401,F403
from zpa_backup_restore.reporting.html_report import *  # noqa: F401,F403
from zpa_backup_restore.storage.backups import *  # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
