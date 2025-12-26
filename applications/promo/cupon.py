from tortoise import models, fields
from tortoise.validators import MaxValueValidator, MinValueValidator

class Cupon(models.Model):
    title = fields.CharField(max_length=100)
    description = fields.TextField(blank=True, null=True)
    cupon = fields.CharField(max_length=100, unique=True)
    discount = fields.IntField(validators=[MinValueValidator(0), MaxValueValidator(100)], default=0)
    up_to = fields.IntField(default=0)
    max_value = fields.IntField(default=100)
    items = fields.ManyToManyField("models.Item", related_name="cupons", blank=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="cupons", on_delete=fields.CASCADE)
    used_by = fields.ManyToManyField("models.User", related_name="used_cupons", blank=True)

    async def can_apply(self, user, item=None):
        used_users = await self.used_by.all()
        if any(u.id == user.id for u in used_users):
            return False, "Coupon already used by this user."

        # Check if coupon is restricted to specific items
        related_items = await self.items.all()
        if related_items:
            if item:
                if not any(i.id == item.id for i in related_items):
                    return False, "Coupon not applicable for this item."
            else:
                return False, "Coupon applicable only for specific items."

        # Validate discount
        if self.discount <= 0 or self.discount > 100:
            return False, "Invalid discount value."

        return True, f"Coupon applied for {self.discount}% discount."

    # async def apply_coupon(self, user, item=None):
    #     valid, msg = await self.can_apply(user, item)
    #     if not valid:
    #         return False, msg
    #
    #     await self.used_by.add(user)
    #     return True, f"Coupon applied successfully. Discount: {self.discount}%"

    async def apply_coupon(self, user, item):
        valid, msg = await self.can_apply(user, item)
        if not valid:
            return False, msg, None

        original_price = item.sell_price
        discount_amount = (original_price * self.discount) / 100
        if self.max_value:
            discount_amount = min(discount_amount, self.max_value)

        final_price = max(original_price - discount_amount, 0)
        await self.used_by.add(user)

        return True, "Coupon applied successfully.", {
            "original_price": original_price,
            "discount_percent": self.discount,
            "discount_amount": round(discount_amount, 2),
            "final_price": round(final_price, 2)
        }