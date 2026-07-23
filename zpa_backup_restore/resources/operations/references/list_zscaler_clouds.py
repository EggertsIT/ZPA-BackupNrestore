"""GET the Zscaler alternative-cloud catalog."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/zpathCloud/getAltClouds",
    documentation_slug="zscaler-clouds/get-all-zscaler-clouds-for-zscaler-cloud",
)
