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




from enum import Enum
from typing import Iterable, Tuple, Optional
from datetime import datetime

from tortoise import models, fields
from tortoise.validators import MaxValueValidator, MinValueValidator


CartItem = Tuple[str, int]  # (category: "food"/"grocery"/"medicine", line_total_amount)


class Voucher(models.Model):
    class VoucherType(str, Enum):
        PRODUCT = "PRODUCT"    # product discount (by category / category-combo)
        SHIPPING = "SHIPPING"  # shipping discount
        EVENT = "EVENT"        # event discount (Puja, Eid, etc.)

    class ProductScope(str, Enum):
        FOOD = "FOOD"
        GROCERY = "GROCERY"
        MEDICINE = "MEDICINE"
        FOOD_GROCERY = "FOOD_GROCERY"
        GROCERY_MEDICINE = "GROCERY_MEDICINE"
        FOOD_MEDICINE = "FOOD_MEDICINE"

    title = fields.CharField(max_length=150)
    description = fields.TextField(null=True)
    voucher_type = fields.CharEnumField(enum_type=VoucherType, max_length=20)
    product_scope = fields.CharEnumField(enum_type=ProductScope, max_length=30, null=True)
    event_name = fields.CharField(max_length=80, null=True)
    min_order_value = fields.IntField(default=0)
    discount_percent = fields.IntField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
    )
    max_discount_amount = fields.IntField(default=0)
    expires_at = fields.DatetimeField(null=True)
    max_redeem = fields.IntField(default=0)
    redeemed_count = fields.IntField(default=0)
    issuer = fields.CharField(max_length=20, default="QUIKLE")
    is_active = fields.BooleanField(default=True)
    def is_valid_now(self) -> bool:
        now = datetime.utcnow()
        if not self.is_active:
            return False
        if self.expires_at and now > self.expires_at:
            return False
        if self.max_redeem > 0 and self.redeemed_count >= self.max_redeem:
            return False
        return True

    def is_eligible(self, cart_total: int) -> bool:
        return self.is_valid_now() and cart_total >= self.min_order_value

    def _scope_categories(self) -> Optional[set[str]]:
        if self.voucher_type != self.VoucherType.PRODUCT or not self.product_scope:
            return None

        if self.product_scope == self.ProductScope.FOOD:
            return {"food"}
        if self.product_scope == self.ProductScope.GROCERY:
            return {"grocery"}
        if self.product_scope == self.ProductScope.MEDICINE:
            return {"medicine"}
        if self.product_scope == self.ProductScope.FOOD_GROCERY:
            return {"food", "grocery"}
        if self.product_scope == self.ProductScope.GROCERY_MEDICINE:
            return {"grocery", "medicine"}
        if self.product_scope == self.ProductScope.FOOD_MEDICINE:
            return {"food", "medicine"}
        return None

    def _items_subtotal(self, cart_items: Iterable[CartItem], categories: Optional[set[str]] = None) -> int:
        subtotal = 0
        for cat, line_total in cart_items:
            if categories is None or cat in categories:
                subtotal += int(line_total)
        return subtotal

    def calculate_savings(self, cart_items: Iterable[CartItem], shipping_fee: int, cart_total: int) -> int:
        if not self.is_eligible(cart_total):
            return 0

        if self.voucher_type == self.VoucherType.SHIPPING:
            base_amount = int(shipping_fee)  # 100% means free delivery
        elif self.voucher_type == self.VoucherType.PRODUCT:
            categories = self._scope_categories()
            base_amount = self._items_subtotal(cart_items, categories)
        else:  # EVENT
            base_amount = self._items_subtotal(cart_items, None)

        discount = (base_amount * int(self.discount_percent)) // 100

        if self.max_discount_amount > 0:
            discount = min(discount, int(self.max_discount_amount))

        return max(0, int(discount))

    @classmethod
    def select_best(
        cls,
        vouchers: Iterable["Voucher"],
        cart_items: Iterable[CartItem],
        shipping_fee: int,
        cart_total: int,
    ) -> Optional["Voucher"]:
        best_voucher = None
        best_savings = 0

        for v in vouchers:
            savings = v.calculate_savings(cart_items, shipping_fee, cart_total)
            if savings > best_savings:
                best_savings = savings
                best_voucher = v

        return best_voucher