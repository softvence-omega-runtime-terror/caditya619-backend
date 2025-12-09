from tortoise import fields, models
from enum import Enum
from tortoise.expressions import Q
from tortoise.functions import Sum, Avg, Count
from applications.customer.models import Order


class PayoutStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class VendorAccount(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.OneToOneField("models.VendorProfile", related_name="account")
    total_earnings = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_withdrow = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    pending_balance = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    commission_earned = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    platform_cost = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    updated_at = fields.DatetimeField(auto_now=True)
    
    async def earnings_calculation(self, start_date, end_date):
        await self.fetch_related("vendor__user")

        vendor_user_id = self.vendor.user_id
        result = await Order.filter(
            Q(vendor_id=vendor_user_id) &
            Q(order_date__gte=start_date) &
            Q(order_date__lte=end_date) &
            Q(status="delivered") 
        ).annotate(
            total_earnings=Sum("total"),
            avg_earnings=Avg("total"),
            total_orders=Count("id")
        ).values("total_earnings", "avg_earnings", "total_orders")

        if not result:
            return {
                "total_earnings": 0,
                "average_earnings": 0,
                "total_orders": 0
            }

        data = result[0]

        return {
            "total_earnings": data.get("total_earnings") or 0,
            "average_earnings": data.get("avg_earnings") or 0,
            "total_orders": data.get("total_orders") or 0
        }

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
