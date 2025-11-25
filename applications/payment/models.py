# applications/payment/models.py

from tortoise import fields, models
from enum import Enum

# ⚠️ CRITICAL: Do NOT import any other model files here!
# Use string references in ForeignKey fields to avoid circular imports

class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

class PaymentProvider(str, Enum):
    """Payment provider enumeration"""
    RAZORPAY = "razorpay"
    STRIPE = "stripe"
    PAYPAL = "paypal"
    COD = "cod"

class Payment(models.Model):
    """Main payment model to track all payment transactions"""
    id = fields.CharField(max_length=255, pk=True)
    
    # Use STRING references, NOT imports
    order = fields.ForeignKeyField(
        "models.Order",
        related_name="payments", 
        on_delete=fields.CASCADE
    )
    user = fields.ForeignKeyField(
        "models.User",
        related_name="payments", 
        on_delete=fields.CASCADE
    )
    
    provider = fields.CharEnumField(PaymentProvider, max_length=20)
    provider_payment_id = fields.CharField(max_length=255, null=True)
    provider_order_id = fields.CharField(max_length=255, null=True)
    provider_signature = fields.CharField(max_length=500, null=True)
    
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    currency = fields.CharField(max_length=3, default="INR")
    status = fields.CharEnumField(PaymentStatus, max_length=20, default=PaymentStatus.PENDING)
    payment_method = fields.CharField(max_length=50, null=True)
    error_code = fields.CharField(max_length=100, null=True)
    error_description = fields.TextField(null=True)
    metadata = fields.JSONField(null=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    completed_at = fields.DatetimeField(null=True)
    
    class Meta:
        table = "payments"

class PaymentRefund(models.Model):
    """Model to handle refund transactions"""
    id = fields.CharField(max_length=255, pk=True)
    payment = fields.ForeignKeyField(
        "models.Payment",
        related_name="refunds", 
        on_delete=fields.CASCADE
    )
    
    provider_refund_id = fields.CharField(max_length=255, null=True)
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    reason = fields.TextField(null=True)
    status = fields.CharEnumField(PaymentStatus, max_length=20, default=PaymentStatus.PENDING)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    processed_at = fields.DatetimeField(null=True)
    
    class Meta:
        table = "payment_refunds"
