import time
from tortoise import fields, models
from fastapi import Depends
from app.token import get_current_user
current_user = Depends(get_current_user)

class CustomerProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField(
        "models.User", related_name="customer_profile", on_delete=fields.CASCADE
    )
    add1 = fields.CharField(max_length=100, null=True)
    add2 = fields.CharField(max_length=100, null=True)
    postal_code = fields.CharField(max_length=20, null=True)

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
    ADDRESS_TYPES = ["HOME", "Office", "OTHERS"]

    id = fields.CharField(max_length=255, pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="shipping_addresses", on_delete=fields.CASCADE
    )
    full_name = fields.CharField(max_length=255, default="")
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

    class Meta:
        table = "customer_shipping_address"
        indexes = [
            ("user_id", "addressType", "is_default"),  # Composite index for queries
        ]

    @classmethod
    async def create_for_profile(cls, profile, **kwargs):
        """
        Create a new shipping address for a user.
        Auto-fills HOME address from profile if not provided.
        Handles make_default logic per address type.
        """
        address_id = f"{profile.id}_addr_{int(time.time() * 1000)}"
        user = await profile.user
        
        address_type = kwargs.get("addressType", "HOME")

        # Auto-fill if HOME and fields are missing
        if address_type == "HOME":
            defaults = {
                "full_name": user.name or "",
                "phone_number": user.phone or "",
                "email": user.email or "",
                "address_line1": ", ".join(filter(None, [profile.add1, profile.add2])),
                "postal_code": profile.postal_code or "",
            }
            # Merge defaults with provided kwargs (kwargs take precedence)
            kwargs = {**defaults, **kwargs}

        # Handle make_default logic
        make_default = kwargs.pop("make_default", False)
        
        if make_default:
            # Unset previous default for THIS address type only
            await cls.filter(
                user_id=user.id,
                addressType=address_type,
                is_default=True
            ).update(is_default=False)
            kwargs["is_default"] = True
        else:
            # Check if this is the first address of this type
            existing_count = await cls.filter(
                user_id=user.id,
                addressType=address_type
            ).count()
            
            # If it's the first address of this type, make it default
            kwargs["is_default"] = existing_count == 0

        address = await cls.create(id=address_id, user_id=user.id, **kwargs)
        return address

    async def set_as_default(self):
        """
        Set this address as default for its type, unset other defaults of the same type.
        """
        # Unset all defaults for this user and address type
        await CustomerShippingAddress.filter(
            user_id=self.user_id,
            addressType=self.addressType,
            is_default=True
        ).exclude(id=self.id).update(is_default=False)
        
        # Set this as default
        self.is_default = True
        await self.save()
        return self

    async def get_defaults(self):
        """Get default values from User and CustomerProfile"""
        await self.fetch_related('user', 'user__customer_profile')
        
        user = await self.user
        defaults = {
            'full_name': user.name or "",
            'phone_number': user.phone or "",
            'email': user.email or "",
            'address_line1': ""
        }
        
        if hasattr(user, 'customer_profile'):
            profile = user.customer_profile
            address_parts = []
            if profile.add1:
                address_parts.append(profile.add1)
            if profile.add2:
                address_parts.append(profile.add2)
            defaults['address_line1'] = ", ".join(address_parts)
            defaults['postal_code'] = profile.postal_code or ""
            
        return defaults

    def __str__(self):
        return f"{self.addressType} - {self.full_name} ({self.id})"