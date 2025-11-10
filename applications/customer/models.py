from tortoise import fields, models
from enum import Enum


class DeliveryType(str, Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PICKUP = "pickup"


class PaymentType(str, Enum):
    COD = "cod"
    CARD = "card"
    WALLET = "wallet"
    UPI = "upi"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "outForDelivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"





class ShippingAddress(models.Model):
    """Shipping Address Model"""
    id = fields.CharField(max_length=255, pk=True)
    full_name = fields.CharField(max_length=255)
    address_line1 = fields.CharField(max_length=500)
    address_line2 = fields.CharField(max_length=500, null=True)
    city = fields.CharField(max_length=255)
    state = fields.CharField(max_length=255)
    postal_code = fields.CharField(max_length=50)
    country = fields.CharField(max_length=255)
    phone_number = fields.CharField(max_length=50)
    is_default = fields.BooleanField(default=False)
    
    class Meta:
        table = "shipping_addresses"


class DeliveryOption(models.Model):
    """Delivery Option Model"""
    id = fields.IntField(pk=True)
    type = fields.CharEnumField(DeliveryType, max_length=50)
    title = fields.CharField(max_length=255)
    description = fields.TextField()
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        table = "delivery_options"


class PaymentMethod(models.Model):
    """Payment Method Model"""
    id = fields.IntField(pk=True)
    type = fields.CharEnumField(PaymentType, max_length=50)
    name = fields.CharField(max_length=255)
    
    class Meta:
        table = "payment_methods"


class Order(models.Model):
    """Order Model"""
    order_id = fields.CharField(max_length=255, pk=True)
    user_id = fields.CharField(max_length=255, index=True)
    
    # Relationships
    shipping_address = fields.ForeignKeyField(
        "models.ShippingAddress", 
        related_name="orders",
        null=True
    )
    delivery_option = fields.ForeignKeyField(
        "models.DeliveryOption", 
        related_name="orders",
        null=True
    )
    payment_method = fields.ForeignKeyField(
        "models.PaymentMethod", 
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
    status = fields.CharEnumField(OrderStatus, max_length=50, default=OrderStatus.PENDING)
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

    def __str__(self):
        return f"Order {self.order_id} - {self.status}"
    


class OrderItem(models.Model):
    """Order Item Model"""
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField("models.Order", related_name="items", on_delete=fields.CASCADE)
    product_id = fields.CharField(max_length=255)
    title = fields.CharField(max_length=500)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    quantity = fields.IntField()
    image_path = fields.CharField(max_length=1000)
    
    class Meta:
        table = "order_items"


# Note: Pydantic serializers are now in schemas.py
# Following the pattern: Model_Pydantic = pydantic_model_creator(Model, name="Model")