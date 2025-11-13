from tortoise import fields, models
import time
from applications.user.models import *

class CustomerProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="customer_profile", on_delete=fields.CASCADE)
    add1 = fields.CharField(max_length=100, null=True, blank=True)
    add2 = fields.CharField(max_length=100, null=True, blank=True)
    postal_code = fields.CharField(max_length=20, null=True, blank=True)

    class Meta:
        table = "cus_profile"
    
    @classmethod
    async def create_for_user(cls, user):
        # Use user's ID as profile ID
        profile = await cls.create(id=user.id, user=user)
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