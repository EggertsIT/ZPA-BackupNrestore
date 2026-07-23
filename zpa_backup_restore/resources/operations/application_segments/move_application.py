"""POST an Application Segment move between Microtenants."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "move",
    "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}/move",
    role="special",
    high_impact=True,
    documentation_slug="application-segment-management/moves-application-of-one-microtenant-to-another",
)
