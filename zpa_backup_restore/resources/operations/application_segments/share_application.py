"""PUT an Application Segment's Microtenant sharing list."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "share",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}/share",
    role="special",
    high_impact=True,
    documentation_slug="application-segment-management/share-the-application-segment-to-microtenants",
)
