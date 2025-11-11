from tortoise import fields, models
from enum import Enum
from applications.user.models import *


# ==================== Enums ====================

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "outForDelivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class DeliveryType(str, Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PICKUP = "pickup"
    URGENT = "urgent"


class PaymentMethodType(str, Enum):
    RAZORPAY = "razorpay"
    COD = "cod"

# ==================== Cart Models ====================

class Cart(models.Model):
    """Cart Model"""
    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField("models.User", related_name="carts")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "carts"


class CartItem(models.Model):
    """Cart Item Model"""
    id = fields.CharField(max_length=255, pk=True)
    cart = fields.ForeignKeyField("models.Cart", related_name="items", on_delete=fields.CASCADE)
    item = fields.ForeignKeyField("models.Item", related_name="cart_items")
    quantity = fields.IntField(default=1)
    added_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "cart_items"


# ==================== Order Models ====================

class Order(models.Model):
    """Order Model"""
    order_id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField("models.User", related_name="orders", index=True)
    
    # Relationships
    shipping_address = fields.ForeignKeyField(
        "models.CustomerShippingAddress", 
        related_name="orders",
        null=True
    )
    delivery_type = fields.CharEnumField(
        DeliveryType,
        max_length=20,  # should be at least as long as your longest enum value
        null=True
    )
    payment_method = fields.CharEnumField(
        PaymentMethodType, 
        related_name="orders",
        null=True
    )
    
    # Pricing
    subtotal = fields.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = fields.DecimalField(max_digits=10, decimal_places=2)
    total = fields.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = fields.CharField(max_length=100, null=True)
    discount = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Order tracking
    order_date = fields.DatetimeField(auto_now_add=True)
    status = fields.CharEnumField(OrderStatus, max_length=50, default=OrderStatus.PENDING, index=True)
    transaction_id = fields.CharField(max_length=255, null=True)
    tracking_number = fields.CharField(max_length=255, null=True, index=True)
    estimated_delivery = fields.DatetimeField(null=True)
    
    # Metadata
    metadata = fields.JSONField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "orders"
        ordering = ["-order_date"]


class OrderItem(models.Model):
    """Order Item Model"""
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField("models.Order", related_name="items", on_delete=fields.CASCADE)
    item_id = fields.ForeignKeyField("models.Item", related_name="order_items")
    title = fields.CharField(max_length=500)
    price = fields.CharField(max_length=50)
    quantity = fields.IntField()
    image_path = fields.CharField(max_length=1000)
    
    class Meta:
        table = "order_item"

