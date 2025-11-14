from tortoise import fields, models
from enum import Enum
from tortoise.models import Model
from applications.user.models import *
from applications.items.models import *
from applications.customer.schemas import *

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

# Keep the Enum separate
class DeliveryTypeEnum(str, Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PICKUP = "pickup"
    URGENT = "urgent"

# Create a proper Tortoise Model for delivery options
# In models.py
class DeliveryOption(Model):
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
    RAZORPAY = "razorpay"
    COD = "cod"
    

class PaymentMethod(Model):
    id = fields.IntField(pk=True)  # Auto-incrementing integer
    type = fields.CharEnumField(PaymentMethodType, max_length=20)
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
    """Order Model"""
    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField("models.User", related_name="orders", index=True)
    cart = fields.ForeignKeyField("models.Cart", related_name="cart_orders", on_delete=fields.SET_NULL, null=True)
    # Relationships
    shipping_address = fields.ForeignKeyField(
        "models.CustomerShippingAddress", 
        related_name="orders",
        null=True
    )
    delivery_type = fields.CharEnumField(
        DeliveryTypeEnum,
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
    id = fields.IntField(pk=True, generated=True)
    order = fields.ForeignKeyField("models.Order", related_name="items", on_delete=fields.CASCADE)
    item_id = fields.ForeignKeyField("models.Item",          related_name="order_items")
    title = fields.CharField(max_length=500)
    price = fields.CharField(max_length=50)
    quantity = fields.IntField()
    image_path = fields.CharField(max_length=1000)
    
    class Meta:
        table = "order_item"



class CustomerProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField(
        "models.User", 
        related_name="customer_profile", 
        on_delete=fields.CASCADE
    )
    add1 = fields.CharField(max_length=100, null=True)
    add2 = fields.CharField(max_length=100, null=True)
    postal_code = fields.CharField(max_length=20, null=True)
    
    class Meta:
        table = "cus_profile"
    
    @classmethod
    async def create_for_user(cls, user):
        """Create profile for user"""
        # Check if profile already exists
        existing = await cls.filter(user=user).first()
        if existing:
            return existing
        
        # Create new profile
        profile = await cls.create(user=user)
        return profile


class CustomerShippingAddress(models.Model):
    """Shipping Address Model"""
    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField("models.User", related_name="shipping_addresses", on_delete=fields.CASCADE)
    
    full_name = fields.CharField(max_length=255, default="")
    address_line1 = fields.CharField(max_length=500, default="")
    address_line2 = fields.CharField(max_length=500, default="")
    city = fields.CharField(max_length=255, null=True)
    state = fields.CharField(max_length=255, null=True)
    country = fields.CharField(max_length=255, null=True)
    phone_number = fields.CharField(max_length=50, default="")
    is_default = fields.BooleanField(default=False)

    class Meta:
        table = "customer_shipping_address"

    @classmethod
    async def create_for_profile(cls, profile: CustomerProfile, **kwargs):
        # Generate shipping address ID based on profile ID
        address_id = f"{profile.id}_addr_{int(time.time() * 1000)}"
        shipping_address = await cls.create(id=address_id, user_id=profile.user.id, **kwargs)
        return shipping_address

    async def get_defaults(self):
        """Get default values from User and CustomerProfile"""
        await self.fetch_related('user', 'user__customer_profile')
        
        defaults = {
            'full_name': self.user.name or "",
            'phone_number': self.user.phone or "",
            'email': self.user.email or "",
            'address_line1': ""
        }
        
        # Get address from CustomerProfile if exists
        if hasattr(self.user, 'customer_profile'):
            profile = self.user.customer_profile
            address_parts = []
            if profile.add1:
                address_parts.append(profile.add1)
            if profile.add2:
                address_parts.append(profile.add2)
            defaults['address_line1'] = ", ".join(address_parts)
        
        return defaults