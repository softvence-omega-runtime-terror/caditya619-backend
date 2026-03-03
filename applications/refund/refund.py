from tortoise import fields
from tortoise.models import Model


class RefundReasonEvidence(Model):
    """Stores customer refund reasons with one or more supporting images."""

    id = fields.IntField(pk=True)
    refund = fields.ForeignKeyField(
        "models.Refund",
        related_name="reason_evidences",
        null=True,
        on_delete=fields.SET_NULL,
    )
    order_id = fields.CharField(max_length=255, index=True)
    user_id = fields.IntField(index=True)
    reason = fields.TextField()
    images = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "refund_reason_evidences"
