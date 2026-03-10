from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional

from tortoise import fields, models
from tortoise.expressions import Q
from tortoise.functions import Avg, Count, Sum

from applications.customer.models import Order, OrderStatus


ZERO_DECIMAL = Decimal("0.00")


def _to_decimal(value) -> Decimal:
    if value is None:
        return ZERO_DECIMAL
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class PayoutStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class Beneficiary(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="beneficiaries")
    beneficiary_id = fields.CharField(128, null=True)
    name = fields.CharField(255)
    bank_account_number = fields.CharField(64)
    bank_ifsc = fields.CharField(64)
    email = fields.CharField(255, null=True)
    phone = fields.CharField(64, null=True)
    is_active = fields.BooleanField(default=True)


class PayoutTransaction(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="payouts")
    beneficiary = fields.ForeignKeyField("models.Beneficiary", related_name="payouts", null=True)
    transfer_id = fields.CharField(128, unique=True)
    amount = fields.DecimalField(max_digits=16, decimal_places=2)
    amount_in_paise = fields.BigIntField(null=True)
    status = fields.CharEnumField(PayoutStatus, default=PayoutStatus.QUEUED)
    cf_response = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    invoice = fields.CharField(355, null=True, blank=True)

    async def save(self, *args, **kwargs):
        is_new = self.id is None
        if self.amount_in_paise is None:
            self.amount_in_paise = int(self.amount * 100)
        await super().save(*args, **kwargs)
        if is_new:
            from app.utils.generate_pdf import generate_payout_pdf

            file_url = await generate_payout_pdf(self)
            self.invoice = file_url
            await super().save(update_fields=["invoice"])


class VendorEarning(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.OneToOneField("models.VendorProfile", related_name="account")
    total_earnings = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_withdrow = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    commission_earned = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    platform_cost = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    available_for_withdraw = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    last_withdrawable_sync_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        # Keep table name unchanged to preserve existing data and compatibility.
        table = "vendoraccount"

    @property
    def pending_balance(self) -> Decimal:
        return (
            _to_decimal(self.total_earnings)
            - _to_decimal(self.total_withdrow)
            - _to_decimal(self.commission_earned)
            - _to_decimal(self.platform_cost)
        )

    @property
    def withdrawable_balance(self) -> Decimal:
        return max(ZERO_DECIMAL, _to_decimal(self.available_for_withdraw))

    @staticmethod
    def _normalize_reference_time(reference_time: Optional[datetime]) -> datetime:
        if reference_time is None:
            return datetime.now(timezone.utc)
        return reference_time

    @staticmethod
    def _delivered_date_filter(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_end: bool = False,
    ) -> Q:
        # Prefer completed_at for delivered orders. Fallback to order_date for legacy rows.
        completed_q = Q(completed_at__isnull=False)
        order_q = Q(completed_at__isnull=True)

        if start_date is not None:
            completed_q &= Q(completed_at__gte=start_date)
            order_q &= Q(order_date__gte=start_date)

        if end_date is not None:
            if include_end:
                completed_q &= Q(completed_at__lte=end_date)
                order_q &= Q(order_date__lte=end_date)
            else:
                completed_q &= Q(completed_at__lt=end_date)
                order_q &= Q(order_date__lt=end_date)

        return completed_q | order_q

    async def _vendor_user_id(self) -> int:
        vendor_profile = await self.vendor
        return vendor_profile.user_id

    async def _sum_delivered_orders(self, extra_filter: Optional[Q] = None) -> Decimal:
        vendor_user_id = await self._vendor_user_id()

        base_filter = Q(vendor_id=vendor_user_id) & Q(status=OrderStatus.DELIVERED.value)
        if extra_filter is not None:
            base_filter &= extra_filter

        result = await Order.filter(base_filter).annotate(total_earnings=Sum("total")).values("total_earnings")
        if not result:
            return ZERO_DECIMAL
        return _to_decimal(result[0].get("total_earnings"))

    async def calculate_total_delivered_earnings(self) -> Decimal:
        # All delivered orders are counted in total earnings.
        return await self._sum_delivered_orders()

    async def calculate_total_withdrawn(self) -> Decimal:
        result = (
            await PayoutTransaction.filter(
                Q(vendor_id=self.vendor_id) & Q(status=PayoutStatus.SUCCESS.value)
            )
            .annotate(total_withdrawn=Sum("amount"))
            .values("total_withdrawn")
        )
        if not result:
            return ZERO_DECIMAL
        return _to_decimal(result[0].get("total_withdrawn"))

    async def calculate_release_window_earnings(
        self, reference_time: Optional[datetime] = None
    ) -> Decimal:
        """
        Earnings eligible in this release batch:
        delivered between 14 days ago (inclusive) and 7 days ago (exclusive).
        """
        reference = self._normalize_reference_time(reference_time)
        window_end = reference - timedelta(days=7)
        window_start = reference - timedelta(days=14)
        window_filter = self._delivered_date_filter(
            start_date=window_start,
            end_date=window_end,
            include_end=False,
        )
        return await self._sum_delivered_orders(window_filter)

    async def calculate_matured_earnings(self, reference_time: Optional[datetime] = None) -> Decimal:
        # Skip last 7 days due to possible returns.
        reference = self._normalize_reference_time(reference_time)
        maturity_cutoff = reference - timedelta(days=7)
        maturity_filter = self._delivered_date_filter(end_date=maturity_cutoff, include_end=False)
        return await self._sum_delivered_orders(maturity_filter)

    async def pending_balance_calculation(self):
        return self.pending_balance

    async def earnings_calculation(self, start_date, end_date):
        vendor_user_id = await self._vendor_user_id()

        order_filter = (
            Q(vendor_id=vendor_user_id)
            & Q(status=OrderStatus.DELIVERED.value)
            & self._delivered_date_filter(
                start_date=start_date,
                end_date=end_date,
                include_end=True,
            )
        )

        result = (
            await Order.filter(order_filter)
            .annotate(
                total_earnings=Sum("total"),
                avg_earnings=Avg("total"),
                total_orders=Count("id"),
            )
            .values("total_earnings", "avg_earnings", "total_orders")
        )

        withdrawal_result = (
            await PayoutTransaction.filter(
                Q(vendor_id=self.vendor_id)
                & Q(created_at__gte=start_date)
                & Q(created_at__lte=end_date)
                & Q(status=PayoutStatus.SUCCESS.value)
            )
            .annotate(total_withdrawn=Sum("amount"))
            .values("total_withdrawn")
        )

        if not result:
            return {
                "total_earnings": ZERO_DECIMAL,
                "average_earnings": ZERO_DECIMAL,
                "total_orders": 0,
                "total_withdrawn": ZERO_DECIMAL,
            }

        data = result[0]
        withdraw = withdrawal_result[0] if withdrawal_result else {"total_withdrawn": ZERO_DECIMAL}

        return {
            "total_earnings": _to_decimal(data.get("total_earnings")),
            "average_earnings": _to_decimal(data.get("avg_earnings")),
            "total_orders": int(data.get("total_orders") or 0),
            "total_withdrawn": _to_decimal(withdraw.get("total_withdrawn")),
        }

    async def refresh_balances(self, reference_time: Optional[datetime] = None) -> Dict[str, Decimal]:
        """
        Recalculate and persist:
        - total_earnings from all delivered orders
        - total_withdrow from successful payouts
        - available_for_withdraw from matured delivered orders (older than 7 days) minus withdrawn
        """
        reference = self._normalize_reference_time(reference_time)
        total_earnings = await self.calculate_total_delivered_earnings()
        matured_earnings = await self.calculate_matured_earnings(reference)
        total_withdrawn = await self.calculate_total_withdrawn()
        release_window_earnings = await self.calculate_release_window_earnings(reference)

        available_for_withdraw = matured_earnings - total_withdrawn
        if available_for_withdraw < ZERO_DECIMAL:
            available_for_withdraw = ZERO_DECIMAL

        self.total_earnings = total_earnings
        self.total_withdrow = total_withdrawn
        self.available_for_withdraw = available_for_withdraw
        self.last_withdrawable_sync_at = reference
        await self.save(
            update_fields=[
                "total_earnings",
                "total_withdrow",
                "available_for_withdraw",
                "last_withdrawable_sync_at",
            ]
        )

        return {
            "total_earnings": total_earnings,
            "matured_earnings": matured_earnings,
            "release_window_earnings": release_window_earnings,
            "total_withdrawn": total_withdrawn,
            "available_for_withdraw": available_for_withdraw,
        }


async def get_or_create_vendor_earning(vendor_profile) -> VendorEarning:
    vendor_earning = await VendorEarning.get_or_none(vendor_id=vendor_profile.id)
    if not vendor_earning:
        vendor_earning = await VendorEarning.create(vendor=vendor_profile)
    return vendor_earning


async def add_money_to_vendor_earning(order_id: str):
    order = await Order.get_or_none(id=order_id)
    if not order:
        return {"error": "Order not found"}

    await order.fetch_related("vendor__vendor_profile")
    vendor_profile = getattr(order.vendor, "vendor_profile", None)
    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_earning = await get_or_create_vendor_earning(vendor_profile)
    summary = await vendor_earning.refresh_balances()

    return {
        "success": True,
        "total_earnings": vendor_earning.total_earnings,
        "available_for_withdraw": vendor_earning.available_for_withdraw,
        "release_window_earnings": summary["release_window_earnings"],
    }


async def refund_money_to_vendor_earning(order_id: str):
    order = await Order.get_or_none(id=order_id)
    if not order:
        return {"error": "Order not found"}

    await order.fetch_related("vendor__vendor_profile")
    vendor_profile = getattr(order.vendor, "vendor_profile", None)
    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_earning = await get_or_create_vendor_earning(vendor_profile)
    summary = await vendor_earning.refresh_balances()

    return {
        "success": True,
        "total_earnings": vendor_earning.total_earnings,
        "available_for_withdraw": vendor_earning.available_for_withdraw,
        "release_window_earnings": summary["release_window_earnings"],
    }


# Backward-compatible aliases for old names used in routes/imports.
VendorAccount = VendorEarning
add_money_to_vendor_account = add_money_to_vendor_earning
refund_money_to_vendor_account = refund_money_to_vendor_earning
