
from app.utils.get_location import get_location_name
from tortoise import fields, models
from enum import Enum

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

# ============================================================
# SUB-ORDER SYSTEM - MODELS
# applications/customer/models.py
# ============================================================
class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "outForDelivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class DeliveryTypeEnum(str, Enum):
    COMBINED = "combined"
    SPLIT = "split"
    URGENT = "urgent"
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
    UPI = "upi"
    ONLINE = "online"

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
# ============================================================
# PARENT ORDER - Main order that contains sub-orders
# ============================================================

class Order(models.Model):
    """
    Parent Order - Contains multiple sub-orders (one per vendor)
    """
    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField("models.User", related_name="orders", index=True)
    
    # Shipping address stored in metadata (not in separate table)
    shipping_address = fields.JSONField(null=True)
    
    # Totals for entire order (sum of all sub-orders)
    subtotal = fields.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = fields.DecimalField(max_digits=10, decimal_places=2)
    total = fields.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = fields.CharField(max_length=100, null=True)
    discount = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Payment information (shared across all sub-orders)
    payment_method = fields.CharEnumField(PaymentMethodType, max_length=20, null=True)
    payment_status = fields.CharField(max_length=50, default="unpaid")
    transaction_id = fields.CharField(max_length=255, null=True)
    cf_order_id = fields.CharField(max_length=255, null=True, index=True)
    payment_session_id = fields.CharField(max_length=255, null=True)
    
    order_date = fields.DatetimeField(auto_now_add=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    metadata = fields.JSONField(null=True)
    
    class Meta:
        table = "orders"
    
    @property
    def can_cancel(self):
        """Order can be cancelled if payment not completed or all sub-orders are pending"""
        if self.payment_status == "unpaid":
            return True
        # Check if all sub-orders are in cancellable state
        return True  # Will check sub-orders in implementation


# ============================================================
# SUB-ORDER - One per vendor
# ============================================================

class SubOrder(models.Model):
    """
    Sub-Order - One per vendor within a parent order
    Each sub-order has its own tracking, vendor, rider, and status
    """
    id = fields.IntField(pk=True)
    
    # Link to parent order
    parent_order = fields.ForeignKeyField(
        "models.Order", 
        related_name="sub_orders", 
        on_delete=fields.CASCADE
    )
    
    # Vendor information
    vendor = fields.ForeignKeyField(
        "models.User", 
        related_name="vendor_sub_orders", 
        on_delete=fields.RESTRICT
    )
    vendor_info = fields.JSONField()  # Preserved vendor details
    
    # Rider assignment
    rider = fields.ForeignKeyField(
        "models.RiderProfile", 
        related_name="assigned_sub_orders", 
        on_delete=fields.CASCADE, 
        null=True
    )
    rider_info = fields.JSONField(null=True)  # Rider details when assigned
    
    # Delivery details
    delivery_type = fields.CharEnumField(DeliveryTypeEnum, max_length=20, null=True)
    delivery_option = fields.JSONField(null=True)  # Store delivery option details
    
    # Sub-order specific totals
    subtotal = fields.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = fields.DecimalField(max_digits=10, decimal_places=2)
    total = fields.DecimalField(max_digits=10, decimal_places=2)
    
    # Status tracking
    status = fields.CharEnumField(OrderStatus, max_length=50, default=OrderStatus.PENDING, index=True)
    tracking_number = fields.CharField(max_length=255, null=True, index=True)
    estimated_delivery = fields.DatetimeField(null=True)
    
    # Timestamps
    accepted_at = fields.DatetimeField(null=True)
    preparing_at = fields.DatetimeField(null=True)
    shipped_at = fields.DatetimeField(null=True)
    delivered_at = fields.DatetimeField(null=True)
    cancelled_at = fields.DatetimeField(null=True)
    
    reason = fields.TextField(null=True)  # Cancellation/rejection reason
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    metadata = fields.JSONField(null=True)
    
    class Meta:
        table = "sub_orders"


# ============================================================
# SUB-ORDER ITEMS
# ============================================================

class SubOrderItem(models.Model):
    """
    Items within a sub-order
    """
    id = fields.IntField(pk=True, generated=True)
    
    sub_order = fields.ForeignKeyField(
        "models.SubOrder", 
        related_name="items", 
        on_delete=fields.CASCADE
    )
    
    item = fields.ForeignKeyField(
        "models.Item", 
        related_name="sub_order_items", 
        on_delete=fields.CASCADE
    )
    
    # Snapshot of item details at time of order
    title = fields.CharField(max_length=500)
    price = fields.CharField(max_length=50)
    quantity = fields.IntField()
    image_path = fields.CharField(max_length=1000)
    
    class Meta:
        table = "sub_order_items"
