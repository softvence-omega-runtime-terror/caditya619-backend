from decimal import Decimal
from typing import Any, Dict, List

from tortoise import fields, models
from tortoise.exceptions import ValidationError


def default_delivery_fee_settings() -> Dict[str, Any]:
    return {
        "base_delivery_fee": {
            "food": 0.0,
            "grocery": 0.0,
            "medicine": 0.0,
        },
        "distance_fee_slabs": [
            {"min_km": 0, "max_km": 3, "fee": 0.0},
            {"min_km": 3, "max_km": 5, "fee": 0.0},
            {"min_km": 5, "max_km": 8, "fee": 0.0},
        ],
        "surge_pricing": {
            "time_slot_rules": [],
            "festival_rules": [],
            "weather_rules": [],
        },
        "free_delivery_threshold": {
            "food": 0.0,
            "grocery": 0.0,
            "medicine": 0.0,
            "cross_category": 0.0,
        },
        "small_cart_fee": {
            "food": {"enabled": False, "threshold": 0.0, "fee": 0.0},
            "grocery": {"enabled": False, "threshold": 0.0, "fee": 0.0},
            "medicine": {"enabled": False, "threshold": 0.0, "fee": 0.0},
        },
        "long_distance_fee": {
            "enabled": False,
            "min_km": 8.0,
            "fee": 0.0,
        },
    }


def default_offers_discount_settings() -> Dict[str, Any]:
    return {
        "first_order_discount": {
            "enabled": False,
            "mode": "percent",
            "value": 0.0,
            "max_cap": 0.0,
            "per_category": {
                "food": {"mode": "percent", "value": 0.0, "max_cap": 0.0},
                "grocery": {"mode": "percent", "value": 0.0, "max_cap": 0.0},
                "medicine": {"mode": "percent", "value": 0.0, "max_cap": 0.0},
            },
        },
        "referral_rewards": {
            "referrer_amount": 0.0,
            "referee_amount": 0.0,
        },
        "combo_offers": [],
        "weekday_weekend_event_offers": {
            "weekday": {"enabled": False, "mode": "percent", "value": 0.0, "max_cap": 0.0},
            "weekend": {"enabled": False, "mode": "percent", "value": 0.0, "max_cap": 0.0},
            "special_event": {"enabled": False, "mode": "percent", "value": 0.0, "max_cap": 0.0},
        },
        "retention_offers": {
            "third_order_offer": {"enabled": False, "mode": "percent", "value": 0.0, "max_cap": 0.0},
            "double_referral_weeks_2_4": {
                "enabled": False,
                "multiplier": 2.0,
            },
        },
    }


def default_order_payment_rules() -> Dict[str, Any]:
    return {
        "minimum_order_value": {
            "food": 0.0,
            "grocery": 0.0,
            "medicine": 0.0,
            "cross_category": 0.0,
        },
        "maximum_order_value": {
            "enabled": False,
            "food": 0.0,
            "grocery": 0.0,
            "medicine": 0.0,
            "cross_category": 0.0,
        },
        "allowed_payment_methods": {
            "upi": True,
            "cards": True,
            "cod": True,
            "net_banking": True,
            "wallet": True,
        },
        "platform_fee": {
            "food": {"mode": "fixed", "value": 0.0},
            "grocery": {"mode": "fixed", "value": 0.0},
            "medicine": {"mode": "fixed", "value": 0.0},
        },
    }


def default_vendor_commission_settings() -> Dict[str, Any]:
    return {
        "restaurant_commission": {
            "global_percent": 0.0,
            "vendor_specific": [],
            "slab_rules": [],
        },
        "pharmacy_commission_percent": 0.0,
        "grocery_margin_percent": 0.0,
        "vendor_payout_cycle": "weekly",
        "commission_exceptions": [],
    }


def default_cancellation_refund_policies() -> Dict[str, Any]:
    return {
        "cancellation_fees": {
            "before_prep": {"mode": "fixed", "value": 0.0},
            "after_prep": {"mode": "percent", "value": 0.0},
            "after_dispatch": {"mode": "percent", "value": 0.0},
        },
        "refund_rules": {
            "auto_refund_upto": 0.0,
            "manual_approval_above": 0.0,
        },
        "late_delivery_compensation": {"mode": "fixed", "value": 0.0},
        "vendor_penalties": [],
    }


def default_customer_experience_settings() -> Dict[str, Any]:
    return {
        "support_contact": {
            "email": "",
            "whatsapp": "",
            "in_app": "",
        },
        "grievance_officer": {
            "name": "",
            "email": "",
            "phone": "",
        },
        "delivery_time_windows": {
            "food": {"start": "00:00", "end": "23:59"},
            "grocery": {"start": "00:00", "end": "23:59"},
            "medicine": {"start": "00:00", "end": "23:59"},
        },
        "app_banners_and_notifications": [],
    }


def default_misc_settings() -> Dict[str, Any]:
    return {
        "tax_rates": {
            "food_gst_percent": 0.0,
            "grocery_gst_percent": 0.0,
            "medicine_gst_percent": 0.0,
            "fee_gst_percent": 0.0,
        },
        "tds_settings": {"enabled": False, "percent": 0.0},
        "invoice_settings": {
            "prefix": "INV",
            "series_start": 1,
            "padding": 6,
        },
        "categories_enabled": {
            "food": True,
            "grocery": True,
            "medicine": True,
        },
        "service_zones": [],
        "blackout_dates": [],
        "festival_holiday_surge_bonus": [],
    }


def default_site_configuration_payload() -> Dict[str, Any]:
    return {
        "delivery_fee_settings": default_delivery_fee_settings(),
        "offers_discount_settings": default_offers_discount_settings(),
        "order_payment_rules": default_order_payment_rules(),
        "vendor_commission_settings": default_vendor_commission_settings(),
        "cancellation_refund_policies": default_cancellation_refund_policies(),
        "customer_experience_settings": default_customer_experience_settings(),
        "misc_settings": default_misc_settings(),
    }


class SiteConfiguration(models.Model):
    id = fields.IntField(pk=True)
    delivery_fee_settings = fields.JSONField(default=default_delivery_fee_settings)
    offers_discount_settings = fields.JSONField(default=default_offers_discount_settings)
    order_payment_rules = fields.JSONField(default=default_order_payment_rules)
    vendor_commission_settings = fields.JSONField(default=default_vendor_commission_settings)
    cancellation_refund_policies = fields.JSONField(default=default_cancellation_refund_policies)
    customer_experience_settings = fields.JSONField(default=default_customer_experience_settings)
    misc_settings = fields.JSONField(default=default_misc_settings)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "site_configuration"

    async def save(self, *args, **kwargs):
        if not self.pk:
            existing = await SiteConfiguration.exists()
            if existing:
                raise ValidationError("Only one SiteConfiguration object is allowed.")
        await super().save(*args, **kwargs)


class PromoCodeSetting(models.Model):
    DISCOUNT_TYPES = (
        ("percent", "Percent"),
        ("flat", "Flat"),
    )

    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    title = fields.CharField(max_length=200, null=True)
    description = fields.TextField(null=True)
    discount_type = fields.CharField(max_length=20, choices=DISCOUNT_TYPES, default="percent")
    discount_value = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    max_cap = fields.DecimalField(max_digits=10, decimal_places=2, null=True)
    usage_limit = fields.IntField(null=True)
    per_user_limit = fields.IntField(default=1)
    used_count = fields.IntField(default=0)
    min_order_value = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    applicable_categories = fields.JSONField(default=list)
    is_cross_category = fields.BooleanField(default=False)
    starts_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    is_active = fields.BooleanField(default=True)
    metadata = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "site_promo_code_settings"

