"""GET enrollment-certificate metadata."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v2/admin/customers/{customer_id}/enrollmentCert",
    pagination="page",
    documentation_slug="enrollment-certificates",
    notes="Inventory metadata only; certificate material and private keys are excluded.",
)
