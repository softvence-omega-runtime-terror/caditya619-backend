import time
from tortoise import fields, models
from fastapi import Depends
from app.token import get_current_user
from applications.items.models import Item
current_user = Depends(get_current_user)

class CustomerProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField(
        "models.User", related_name="customer_profile", on_delete=fields.CASCADE
    )
    add1 = fields.CharField(max_length=100, null=True)
    add2 = fields.CharField(max_length=100, null=True)
    postal_code = fields.CharField(max_length=20, null=True)

    customer_lat = fields.FloatField(null=True)
    customer_lng = fields.FloatField(null=True)

    class Meta:
        table = "cus_profile"

    @classmethod
    async def create_for_user(cls, user):
        existing = await cls.filter(user=user).first()
        if existing:
            return existing
        profile = await cls.create(user=user)
        return profile
    
class CustomerShippingAddress(models.Model):
    """Shipping Address Model"""
    ADDRESS_TYPES = ["HOME", "OFFICE", "OTHERS"]
    
    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="shipping_addresses", on_delete=fields.CASCADE
    )

    full_name = fields.CharField(max_length=255, default="")
    flat_house_building = fields.CharField(max_length=255, default="")
    floor_number = fields.CharField(max_length=100, default="")
    nearby_landmark = fields.CharField(max_length=500, default="")
    address_line1 = fields.CharField(max_length=500, default="")
    address_line2 = fields.CharField(max_length=500, default="")
    city = fields.CharField(max_length=255, null=True)
    state = fields.CharField(max_length=255, null=True)
    country = fields.CharField(max_length=255, null=True)
    postal_code = fields.CharField(max_length=20, null=True)
    phone_number = fields.CharField(max_length=50, default="")
    email = fields.CharField(max_length=100, default="")
    is_default = fields.BooleanField(default=False)
    addressType = fields.CharField(max_length=50, default="HOME")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)




    async def save(self, *args, **kwargs):
        is_new = not self.id
        await super().save(*args, **kwargs)
        if self.is_default:
            await CustomerShippingAddress.filter(
                user_id=self.user_id
            ).exclude(id=self.id).update(is_default=False)

        return {
            "status": True,
            "message": "Active address updated successfully",
            "address_id": self.id
        }

    class Meta:
        table = "customer_shipping_address"
        indexes = [
            ("user_id", "addressType", "is_default"),  # Composite index for queries
        ]

    def __str__(self):
        return f"{self.addressType} - {self.full_name} ({self.id})"