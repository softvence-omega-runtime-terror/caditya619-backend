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