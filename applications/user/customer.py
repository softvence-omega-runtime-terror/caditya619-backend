import time
from tortoise import fields, models

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
    zonal_or_postal_code = fields.CharField(max_length=20, null=True)
    phone_number = fields.CharField(max_length=50, default="")
    customer_email = fields.CharField(max_length=100, default="")
    is_default = fields.BooleanField(default=False)
    addressType = fields.CharField(max_length=50, default="HOME")

    class Meta:
        table = "customer_shipping_address"

    @classmethod
    async def create_for_profile(cls, profile: CustomerProfile, **kwargs):
        """
        Create a new shipping address for a user.
        Auto-fills HOME address from profile if not provided.
        Handles make_default logic.
        """
        address_id = f"{profile.id}_addr_{int(time.time() * 1000)}"
        user = await profile.user
        print("uuuuuuuuuuuuuuuuuuuuu========",user.name)

        # Auto-fill if HOME and fields are missing
        if kwargs.get("addressType", "HOME") == "HOME":
            defaults = {
                "full_name": user.name or "",
                "phone_number": user.phone or "",
                "email": user.email or "",
                "address_line1": ", ".join(filter(None, [profile.add1, profile.add2])),
                "postal_code": profile.postal_code,
            }
            kwargs = {**defaults, **kwargs}

        # Handle make_default
        make_default = kwargs.pop("make_default", False)
        if make_default:
            # Unset previous default
            await cls.filter(user=user, is_default=True).update(is_default=False)
            kwargs["is_default"] = True
        else:
            kwargs["is_default"] = False

        address = await cls.create(id=address_id, user_id=user.id, **kwargs)
        return address

    async def set_as_default(self):
        """Set this address as default, unset others"""
        await CustomerShippingAddress.filter(user_id=self.user.id, is_default=True).update(is_default=False)
        self.is_default = True
        await self.save()
        return self

    async def get_defaults(self):
        """Get default values from User and CustomerProfile"""
        await self.fetch_related('user', 'user__customer_profile')
        defaults = {
            'full_name': self.user.name or "",
            'phone_number': self.user.phone or "",
            'email': self.user.email or "",
            'address_line1': ""
        }
        if hasattr(self.user, 'customer_profile'):
            profile = self.user.customer_profile
            address_parts = []
            if profile.add1:
                address_parts.append(profile.add1)
            if profile.add2:
                address_parts.append(profile.add2)
            defaults['address_line1'] = ", ".join(address_parts)
        return defaults
