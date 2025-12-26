from typing import Tuple

from tortoise import models, fields
from tortoise.validators import MaxValueValidator, MinValueValidator

class Cupon(models.Model):
    title = fields.CharField(max_length=100)
    description = fields.TextField(blank=True, null=True)
    cupon = fields.CharField(max_length=100, unique=True)
    discount = fields.IntField(validators=[MinValueValidator(0), MaxValueValidator(100)], default=0)
    up_to = fields.IntField(default=0)
    max_value = fields.IntField(default=100)
    uses_limit = fields.IntField(default=0)
    # items = fields.ManyToManyField("models.Item", related_name="cupons", blank=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="cupons", on_delete=fields.CASCADE)
    used_by = fields.ManyToManyField("models.User", related_name="used_cupons", blank=True)

    async def can_apply(self, user) -> Tuple[bool, str]:
        # Check if user has already used the coupon
        used_users = await self.used_by.all()
        if any(u.id == user.id for u in used_users):
            return False, "Coupon already used by this user."

        # Check uses limit (0 = unlimited)
        if self.uses_limit > 0 and len(used_users) >= self.uses_limit:
            return False, "Coupon usage limit reached."

        # Check discount validity
        if self.discount <= 0 or self.discount > 100:
            return False, "Invalid discount value."

        return True, f"Coupon can be applied for {self.discount}% discount."

    async def apply_coupon(self, user) -> Tuple[bool, str]:
        valid, msg = await self.can_apply(user)
        if not valid:
            return False, msg

        await self.used_by.add(user)
        return True, f"Coupon applied successfully. Discount: {self.discount}%"
