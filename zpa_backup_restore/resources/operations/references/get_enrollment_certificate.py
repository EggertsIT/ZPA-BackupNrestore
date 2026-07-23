"""GET one enrollment certificate.

The operation is cataloged for API audit coverage but is not used by the backup
service because the list response supplies the safe reference metadata.
"""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/enrollmentCert/{id}",
    documentation_slug="enrollment-certificates/gets-the-enrollment-certificate-details-for-the-specified-id",
    notes="Not called during backup; detail responses can contain certificate material.",
)
