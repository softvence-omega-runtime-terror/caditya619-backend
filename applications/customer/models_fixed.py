from tortoise import fields, models
from enum import Enum
from tortoise.models import Model

# ❌ REMOVE THESE LINES:
# from applications.user.models import *
# from applications.items.models import *
# from applications.payment.models import *
# from applications.customer.schemas import *

# ✅ Use string references in ForeignKey fields instead!

# ==================== Enums ====================
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class DeliveryTypeEnum(str, Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PICKUP = "pickup"
    URGENT = "urgent"

# ... rest of your models (keep everything else the same)
