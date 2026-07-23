"""GET all LSS configurations."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig",
    pagination="page",
    documentation_slug="siem-config/gets-all-lss-configurations-for-the-specified-customer",
)
