
from app.utils.get_location import get_location_name
from tortoise import fields, models
from enum import Enum
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
    id = fields.CharField(max_length=255, pk=True)
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
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    prepire_time = fields.IntField(null=True)
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

    payment_status = fields.CharField(
        max_length=50, 
        default="unpaid"
    )  # Values: "unpaid", "paid", "failed", "expired", "cod"
    
    # shipping_address_id = fields.ForeignKeyField(
    #     "models.CustomerShippingAddress",
    #     related_name="orders",
    #     null=True  # ← Make this nullable
    # )
    # Tracks if payment is done: "unpaid", "paid", "failed"
    
    cf_order_id = fields.CharField(max_length=255, null=True)
    # Cashfree's order ID (they give us this)
    
    payment_session_id = fields.CharField(max_length=255, null=True)
    # Session ID to track the payment

    async def get_all_vendors_locations(self):
        """
        Get ALL vendor locations if order has items from multiple vendors
        """
        
        # Step 1: Load all data
        await self.fetch_related("items__item__vendor__vendor_profile")
        
        # Step 2: Collect all unique vendors
        vendors_locations = []
        seen_vendor_ids = set()  # To avoid duplicates
        
        # Step 3: Loop through all order items
        for order_item in self.items:
            vendor = order_item.item.vendor
            
            # Skip if we already processed this vendor
            if vendor.id in seen_vendor_ids:
                continue
            
            # Check if vendor has profile and location
            if hasattr(vendor, 'vendor_profile'):
                profile = vendor.vendor_profile
                
                if profile.latitude and profile.longitude:
                    vendors_locations.append({
                        'vendor_id': vendor.id,
                        'vendor_name': profile.owner_name,
                        'latitude': profile.latitude,
                        'longitude': profile.longitude,
                        'is_active': profile.is_active
                    })
                    
                    seen_vendor_ids.add(vendor.id)
        
        return vendors_locations

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



