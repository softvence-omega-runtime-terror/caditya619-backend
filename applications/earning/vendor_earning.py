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

class VendorAccount(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.OneToOneField("models.VendorProfile", related_name="account")
    total_earnings = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_withdrow = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    commission_earned = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    platform_cost = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    updated_at = fields.DatetimeField(auto_now=True)
    
    async def pending_balance_calculation(self):
        pending_balance = self.total_earnings - self.total_withdrow - self.commission_earned - self.platform_cost
        return pending_balance
    
    
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
        
        withdrawal_result = await PayoutTransaction.filter(
            Q(vendor_id=vendor_user_id) &
            Q(created_at__gte=start_date) &
            Q(created_at__lte=end_date) &
            Q(status="success")
        ).annotate(total_withdrawn=Sum("amount")).values("total_withdrawn")

        if not result:
            return {
                "total_earnings": 0,
                "average_earnings": 0,
                "total_orders": 0
            }

        data = result[0]
        withdraw = withdrawal_result[0] if withdrawal_result else {"total_withdrawn": 0}

        return {
            "total_earnings": data.get("total_earnings") or 0,
            "average_earnings": data.get("avg_earnings") or 0,
            "total_orders": data.get("total_orders") or 0,
            "total_withdrawn": withdraw.get("total_withdrawn") or 0
        }


async def add_money_to_vendor_account(order_id: str):
    order = await Order.get_or_none(id=order_id)
    if not order:
        return {"error": "Order not found"}
    await order.fetch_related("vendor__vendor_profile")
    vendor_profile = getattr(order.vendor, "vendor_profile", None)
    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_account = await VendorAccount.get_or_none(vendor_id=vendor_profile.id)
    if not vendor_account:
        vendor_account = await VendorAccount.create(vendor=vendor_profile, total_earnings=0)

    vendor_account.total_earnings += order.total
    await vendor_account.save()

    print(f"Added {order.total} to VendorAccount of vendor {vendor_profile.id}")
    return {"success": True, "total_earnings": vendor_account.total_earnings}


async def refund_money_to_vendor_account(order_id: str):
    order = await Order.get_or_none(id=order_id)
    if not order:
        return {"error": "Order not found"}
    await order.fetch_related("vendor__vendor_profile")
    vendor_profile = getattr(order.vendor, "vendor_profile", None)
    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_account = await VendorAccount.get_or_none(vendor_id=vendor_profile.id)
    if not vendor_account:
        vendor_account = await VendorAccount.create(vendor=vendor_profile, total_earnings=0)

    vendor_account.total_earnings -= order.total
    await vendor_account.save()

    print(f"Added {order.total} to VendorAccount of vendor {vendor_profile.id}")
    return {"success": True, "total_earnings": vendor_account.total_earnings}