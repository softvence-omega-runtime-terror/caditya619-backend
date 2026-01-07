from tortoise import fields
from tortoise.models import Model



class Refund(Model):
    """Refund tracking"""
    id = fields.CharField(max_length=255, pk=True)
    order_id = fields.CharField(max_length=255, index=True)
    user_id = fields.IntField(index=True)
    
    refund_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    cancellation_fee = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
    original_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    
    status = fields.CharField(max_length=50, default="initiated", index=True)
    reason = fields.CharField(max_length=100, default="customer_cancellation")
    
    payment_method = fields.CharField(max_length=50, null=True)
    gateway_refund_id = fields.CharField(max_length=255, null=True, unique=True)
    
    expected_completion = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "refunds"


class RefundLog(Model):
    """Audit trail"""
    refund_id = fields.CharField(max_length=255, index=True)
    order_id = fields.CharField(max_length=255)
    action = fields.CharField(max_length=100)
    old_status = fields.CharField(max_length=50, null=True)
    new_status = fields.CharField(max_length=50, null=True)
    actor_type = fields.CharField(max_length=50)  # customer, gateway, system
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "refund_logs"



class CancellationReason(Model):
    """Predefined cancellation reasons"""
    id = fields.IntField(pk=True)  # Auto-incrementing integer
    reason = fields.CharField(max_length=255, unique=True)
    order_id = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "cancellation_reasons"



class ReportAndIssue(Model):
    """Reports and issues logged by users"""
    id = fields.IntField(pk=True)  # Auto-incrementing integer
    order_id = fields.CharField(max_length=255, index=True)
    reason = fields.CharField(max_length=100)  # e.g., "refund", "item_missing"
    details = fields.TextField(null=True)
    image = fields.CharField(max_length=255, null=True)  # URL or path to image
    transection_id = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "reports_and_issues"