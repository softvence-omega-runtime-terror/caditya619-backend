from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Tuple

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

CartItem = Tuple[str, int]


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
        used_users = await self.used_by.all()
        if any(u.id == user.id for u in used_users):
            return False, "Coupon already used by this user."

        if self.uses_limit > 0 and len(used_users) >= self.uses_limit:
            return False, "Coupon usage limit reached."

        if self.discount <= 0 or self.discount > 100:
            return False, "Invalid discount value."

        return True, f"Coupon can be applied for {self.discount}% discount."

    async def apply_coupon(self, user) -> Tuple[bool, str]:
        valid, msg = await self.can_apply(user)
        if not valid:
            return False, msg

        await self.used_by.add(user)
        return True, f"Coupon applied successfully. Discount: {self.discount}%"


class Voucher(models.Model):
    class VoucherType(str, Enum):
        PRODUCT = "PRODUCT"
        SHIPPING = "SHIPPING"
        EVENT = "EVENT"

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
    used_by = fields.ManyToManyField("models.User", related_name="used_voucher", blank=True)
    is_active = fields.BooleanField(default=True)

    @staticmethod
    def _enum_value(value):
        return value.value if isinstance(value, Enum) else value

    @staticmethod
    def _normalized_category(value: str) -> str:
        return str(value or "").strip().lower()

    def _normalized_expires_at(self) -> Optional[datetime]:
        if self.expires_at is None:
            return None
        if self.expires_at.tzinfo is not None:
            return self.expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        return self.expires_at

    def is_valid_now(self) -> bool:
        now = datetime.utcnow()
        expires_at = self._normalized_expires_at()
        if not self.is_active:
            return False
        if expires_at and now > expires_at:
            return False
        if self.max_redeem > 0 and self.redeemed_count >= self.max_redeem:
            return False
        return True

    def is_eligible(self, cart_total: int) -> bool:
        return self.is_valid_now() and int(cart_total) >= int(self.min_order_value or 0)

    def _scope_categories(self) -> Optional[set[str]]:
        voucher_type = self._enum_value(self.voucher_type)
        if voucher_type != self.VoucherType.PRODUCT.value or not self.product_scope:
            return None

        product_scope = self._enum_value(self.product_scope)
        if product_scope == self.ProductScope.FOOD.value:
            return {"food"}
        if product_scope == self.ProductScope.GROCERY.value:
            return {"grocery"}
        if product_scope == self.ProductScope.MEDICINE.value:
            return {"medicine"}
        if product_scope == self.ProductScope.FOOD_GROCERY.value:
            return {"food", "grocery"}
        if product_scope == self.ProductScope.GROCERY_MEDICINE.value:
            return {"grocery", "medicine"}
        if product_scope == self.ProductScope.FOOD_MEDICINE.value:
            return {"food", "medicine"}
        return None

    def _items_subtotal(self, cart_items: Iterable[CartItem], categories: Optional[set[str]] = None) -> int:
        normalized_categories = None if categories is None else {c.lower() for c in categories}
        subtotal = 0
        for category, line_total in cart_items:
            category_key = self._normalized_category(category)
            if normalized_categories is None or category_key in normalized_categories:
                subtotal += int(line_total)
        return subtotal

    def calculate_savings(self, cart_items: Iterable[CartItem], shipping_fee: int, cart_total: int) -> int:
        if not self.is_eligible(cart_total):
            return 0

        voucher_type = self._enum_value(self.voucher_type)
        if voucher_type == self.VoucherType.SHIPPING.value:
            base_amount = int(shipping_fee)
        elif voucher_type == self.VoucherType.PRODUCT.value:
            categories = self._scope_categories()
            base_amount = self._items_subtotal(cart_items, categories)
        else:
            base_amount = self._items_subtotal(cart_items, None)

        discount = (base_amount * int(self.discount_percent or 0)) // 100

        if self.max_discount_amount > 0:
            discount = min(discount, int(self.max_discount_amount))

        return max(0, int(discount))

    async def can_apply(
        self,
        user,
        cart_items: Iterable[CartItem],
        shipping_fee: int,
        cart_total: int,
    ) -> Tuple[bool, str, int]:
        if not self.is_valid_now():
            return False, "Voucher is not valid right now.", 0

        already_used = await self.used_by.filter(id=user.id).exists()
        if already_used:
            return False, "Voucher already used by this user.", 0

        savings = self.calculate_savings(cart_items, shipping_fee, cart_total)
        if savings <= 0:
            return False, "Voucher is not eligible for this cart.", 0

        return True, "Voucher can be applied.", int(savings)

    async def apply_voucher(
        self,
        user,
        cart_items: Iterable[CartItem],
        shipping_fee: int,
        cart_total: int,
    ) -> Tuple[bool, str, int]:
        is_valid, message, savings = await self.can_apply(user, cart_items, shipping_fee, cart_total)
        if not is_valid:
            return False, message, 0

        await self.used_by.add(user)
        self.redeemed_count = int(self.redeemed_count or 0) + 1
        await self.save(update_fields=["redeemed_count"])
        return True, "Voucher applied successfully.", int(savings)

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

        for voucher in vouchers:
            savings = voucher.calculate_savings(cart_items, shipping_fee, cart_total)
            if savings > best_savings:
                best_savings = savings
                best_voucher = voucher

        return best_voucher