from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Dict, Optional, Tuple
from tortoise.validators import MinValueValidator, MaxValueValidator

from tortoise import Tortoise, fields, models
from tortoise.expressions import Q
from tortoise.exceptions import OperationalError
from tortoise.functions import Avg, Count, Sum

from applications.customer.models import Order, OrderStatus


ZERO_DECIMAL = Decimal("0.00")
HUNDRED_DECIMAL = Decimal("100")
MONEY_QUANTIZER = Decimal("0.01")
_VENDOR_ACCOUNT_SCHEMA_CHECKED = False


def _to_decimal(value) -> Decimal:
    if value is None:
        return ZERO_DECIMAL
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_money(value) -> Decimal:
    return _to_decimal(value).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


class PayoutStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class AutoPayoutStatus(str, Enum):
    MANUAL = "manual"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Beneficiary(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="beneficiaries")
    beneficiary_id = fields.CharField(128, null=True)
    name = fields.CharField(255)
    bank_account_number = fields.CharField(64)
    bank_ifsc = fields.CharField(64)
    email = fields.CharField(255, null=True)
    phone = fields.CharField(64, null=True)
    auto_payout_amount = fields.DecimalField(max_digits=16, decimal_places=2, default=500, validators=[MinValueValidator(500), MaxValueValidator(5000)])
    auto_payout_status = fields.CharEnumField(AutoPayoutStatus, default=AutoPayoutStatus.MANUAL)
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
            self.amount_in_paise = int(_to_money(self.amount) * 100)
        await super().save(*args, **kwargs)
        if is_new:
            from app.utils.generate_pdf import generate_payout_pdf

            file_url = await generate_payout_pdf(self)
            self.invoice = file_url
            await super().save(update_fields=["invoice"])


class VendorAccount(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.OneToOneField("models.VendorProfile", related_name="account")
    total_earnings = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_withdrow = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    available_for_withdraw = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    last_withdrawable_sync_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "vendoraccount"

    @property
    def pending_balance(self) -> Decimal:
        # total_earnings already excludes commission
        return _to_money(_to_decimal(self.total_earnings) - _to_decimal(self.total_withdrow))

    @property
    def withdrawable_balance(self) -> Decimal:
        return max(ZERO_DECIMAL, _to_money(self.available_for_withdraw))

    @staticmethod
    def _normalize_reference_time(reference_time: Optional[datetime]) -> datetime:
        if reference_time is None:
            return datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            return reference_time.replace(tzinfo=timezone.utc)
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
        await self.fetch_related("vendor")
        return self.vendor.user_id

    async def _commission_percent(self) -> Decimal:
        await self.fetch_related("vendor")
        raw_value = getattr(self.vendor, "commission", ZERO_DECIMAL)
        percent = _to_decimal(raw_value)
        if percent < ZERO_DECIMAL:
            return ZERO_DECIMAL
        if percent > HUNDRED_DECIMAL:
            return HUNDRED_DECIMAL
        return percent

    async def _sum_delivered_orders(self, extra_filter: Optional[Q] = None) -> Decimal:
        vendor_user_id = await self._vendor_user_id()

        base_filter = Q(vendor_id=vendor_user_id) & Q(status=OrderStatus.DELIVERED.value)
        if extra_filter is not None:
            base_filter &= extra_filter

        result = await Order.filter(base_filter).annotate(gross_total=Sum("total")).values("gross_total")
        if not result:
            return ZERO_DECIMAL
        return _to_money(result[0].get("gross_total"))

    async def _net_from_delivered_orders(
        self, extra_filter: Optional[Q] = None
    ) -> Tuple[Decimal, Decimal, Decimal]:
        gross_total = await self._sum_delivered_orders(extra_filter)
        commission_percent = await self._commission_percent()
        commission_amount = _to_money((gross_total * commission_percent) / HUNDRED_DECIMAL)
        net_total = _to_money(gross_total - commission_amount)
        if net_total < ZERO_DECIMAL:
            net_total = ZERO_DECIMAL
        return gross_total, commission_amount, net_total

    async def calculate_total_delivered_earnings(self) -> Decimal:
        _, _, net_total = await self._net_from_delivered_orders()
        return net_total

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
        return _to_money(result[0].get("total_withdrawn"))

    async def calculate_release_window_earnings(
        self, reference_time: Optional[datetime] = None
    ) -> Decimal:
        """
        Eligible release batch:
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
        _, _, net_total = await self._net_from_delivered_orders(window_filter)
        return net_total

    async def calculate_matured_earnings(self, reference_time: Optional[datetime] = None) -> Decimal:
        # Last 7 days are intentionally held for potential refunds.
        reference = self._normalize_reference_time(reference_time)
        maturity_cutoff = reference - timedelta(days=7)
        maturity_filter = self._delivered_date_filter(end_date=maturity_cutoff, include_end=False)
        _, _, net_total = await self._net_from_delivered_orders(maturity_filter)
        return net_total

    async def pending_balance_calculation(self) -> Decimal:
        return self.pending_balance

    async def earnings_calculation(self, start_date, end_date) -> Dict[str, Decimal]:
        vendor_user_id = await self._vendor_user_id()
        commission_percent = await self._commission_percent()

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
                gross_total=Sum("total"),
                gross_avg=Avg("total"),
                total_orders=Count("id"),
            )
            .values("gross_total", "gross_avg", "total_orders")
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
        gross_total = _to_money(data.get("gross_total"))
        gross_avg = _to_money(data.get("gross_avg"))

        commission_total = _to_money((gross_total * commission_percent) / HUNDRED_DECIMAL)
        commission_avg = _to_money((gross_avg * commission_percent) / HUNDRED_DECIMAL)

        net_total = _to_money(gross_total - commission_total)
        net_avg = _to_money(gross_avg - commission_avg)

        if net_total < ZERO_DECIMAL:
            net_total = ZERO_DECIMAL
        if net_avg < ZERO_DECIMAL:
            net_avg = ZERO_DECIMAL

        withdraw = withdrawal_result[0] if withdrawal_result else {"total_withdrawn": ZERO_DECIMAL}

        return {
            "total_earnings": net_total,
            "average_earnings": net_avg,
            "total_orders": int(data.get("total_orders") or 0),
            "total_withdrawn": _to_money(withdraw.get("total_withdrawn")),
        }

    async def refresh_balances(self, reference_time: Optional[datetime] = None) -> Dict[str, Decimal]:
        """
        Recalculate and persist:
        1) total_earnings = all delivered totals - commission
        2) total_withdrow = all successful withdrawals
        3) available_for_withdraw = matured(total_earnings older than 7 days) - total_withdrow
        4) 7-day hold: last 7 days are excluded; release window is 14d -> 7d
        """
        reference = self._normalize_reference_time(reference_time)

        _, total_commission, total_net_earnings = await self._net_from_delivered_orders()
        _, _, matured_net_earnings = await self._net_from_delivered_orders(
            self._delivered_date_filter(end_date=reference - timedelta(days=7), include_end=False)
        )
        _, _, release_window_earnings = await self._net_from_delivered_orders(
            self._delivered_date_filter(
                start_date=reference - timedelta(days=14),
                end_date=reference - timedelta(days=7),
                include_end=False,
            )
        )
        total_withdrawn = await self.calculate_total_withdrawn()

        available_for_withdraw = _to_money(matured_net_earnings - total_withdrawn)
        if available_for_withdraw < ZERO_DECIMAL:
            available_for_withdraw = ZERO_DECIMAL

        self.total_earnings = total_net_earnings
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
            "total_earnings": total_net_earnings,
            "matured_earnings": matured_net_earnings,
            "release_window_earnings": release_window_earnings,
            "total_withdrawn": total_withdrawn,
            "available_for_withdraw": available_for_withdraw,
        }


async def get_or_create_vendor_account(vendor_profile) -> VendorAccount:
    global _VENDOR_ACCOUNT_SCHEMA_CHECKED

    if not _VENDOR_ACCOUNT_SCHEMA_CHECKED:
        try:
            await VendorAccount.exists()
        except OperationalError as exc:
            err = str(exc).lower()
            if "1146" in err and "vendoraccount" in err and "doesn't exist" in err:
                await Tortoise.generate_schemas(safe=True)
            else:
                raise
        _VENDOR_ACCOUNT_SCHEMA_CHECKED = True

    vendor_account = await VendorAccount.get_or_none(vendor_id=vendor_profile.id)
    if not vendor_account:
        vendor_account = await VendorAccount.create(vendor=vendor_profile)
    return vendor_account


