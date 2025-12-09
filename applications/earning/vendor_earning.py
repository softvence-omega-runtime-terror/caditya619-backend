from tortoise import fields, models
from enum import Enum

class PayoutStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class VendorAccount(models.Model):
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.VendorProfile", related_name="ledgers")
    total_earnings = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    withdrawable_balance = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    pending_balance = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    commission_earned = fields.DecimalField(max_digits=16, decimal_places=2, default=0)
    updated_at = fields.DatetimeField(auto_now=True)

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
