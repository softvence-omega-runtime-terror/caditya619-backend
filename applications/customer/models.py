
from app.utils.get_location import get_location_name
from tortoise import fields, models
from enum import Enum
# ==================== Enums ====================

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    PREPARED = "prepared"
    OUT_FOR_DELIVERY = "outForDelivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refundRequested"
    REFUND_APPROVED = "refundApproved"
    REFUNDED = "refunded"


class DeliveryTypeEnum(str, Enum):
    COMBINED = "combined"
    SPLIT = "split"
    URGENT = "urgent"

# Create a proper Tortoise Model for delivery options
# In models.py
class DeliveryOption(models.Model):
    id = fields.IntField(pk=True)  # Auto-incrementing integer
    type = fields.CharEnumField(DeliveryTypeEnum, max_length=20)
    title = fields.CharField(max_length=100)
    description = fields.TextField()
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "delivery_option"

class PaymentMethodType(str, Enum):
    CASHFREE = "cashfree"
    COD = "cod"
    

class PaymentMethod(models.Model):
    id = fields.IntField(pk=True)  # Auto-incrementing integer
    type = fields.CharEnumField(PaymentMethodType, max_length=20, default=PaymentMethodType.COD)
    title = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "payment_method"

# ==================== Order Models ====================

class Order(models.Model):
    id = fields.CharField(max_length=255, pk=True)
    parent_order_id = fields.CharField(max_length=255, null=True, index=True)  # NEW: For grouping orders
    user = fields.ForeignKeyField("models.User", related_name="orders", index=True)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="assigned_orders", on_delete=fields.CASCADE, null=True)

    vendor = fields.ForeignKeyField("models.User", related_name="vendor_orders", on_delete=fields.RESTRICT, null=True)

    shipping_address = fields.ForeignKeyField(
        "models.CustomerShippingAddress",
        related_name="orders",
        null=True
    )
    
    delivery_type = fields.CharEnumField(
        DeliveryTypeEnum,
        max_length=20,
        null=True
    )
    
    payment_method = fields.CharEnumField(
        PaymentMethodType,
        max_length=20,
        null=True
    )
    
    subtotal = fields.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = fields.DecimalField(max_digits=10, decimal_places=2)
    total = fields.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = fields.CharField(max_length=100, null=True)
    discount = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    order_date = fields.DatetimeField(auto_now_add=True)
    status = fields.CharEnumField(OrderStatus, max_length=50, default=OrderStatus.PENDING, index=True)
    transaction_id = fields.CharField(max_length=255, null=True)
    tracking_number = fields.CharField(max_length=255, null=True, index=True)
    estimated_delivery = fields.DatetimeField(null=True)
    
    metadata = fields.JSONField(null=True)
    prepare_time = fields.IntField(null=True)
    reason = fields.TextField(null=True)
    pickup_distance_km = fields.FloatField(null= True)
    pickup_time = fields.DatetimeField(null=True)
    eta_minutes = fields.IntField(null =True)
    base_rate = fields.DecimalField(max_digits=10, decimal_places=2, default=44.00)
    distance_bonus = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    offered_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    accepted_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    is_on_time = fields.BooleanField(null=True)
    is_combined = fields.BooleanField(default=False)
    combined_pickups = fields.JSONField(null=True)  # list of dicts: [{"name": "Thai Spice", "amount": 44}]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    payment_status = fields.CharField(
        max_length=50, 
        default="unpaid"
    )  # Values: "unpaid", "paid", "failed", "expired", "cod"

    
    cf_order_id = fields.CharField(max_length=255, null=True)
    # Cashfree's order ID (they give us this)
    payment_session_id = fields.CharField(max_length=255, null=True)
    # Session ID to track the payment
    class Meta:
        table = "orders"
        ordering = ["-order_date"]


class OrderItem(models.Model):
    id = fields.IntField(pk=True, generated=True)
    order = fields.ForeignKeyField("models.Order", related_name="items", on_delete=fields.CASCADE)
    item = fields.ForeignKeyField("models.Item", related_name="order_items", on_delete=fields.CASCADE)
    title = fields.CharField(max_length=500)
    price = fields.CharField(max_length=50)
    quantity = fields.IntField()
    image_path = fields.CharField(max_length=1000)
    
    class Meta:
        table = "order_item"



