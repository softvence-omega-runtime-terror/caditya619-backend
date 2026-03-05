from typing import Any, Dict

from tortoise import fields, models
from tortoise.exceptions import ValidationError


def default_delivery_fee_settings() -> Dict[str, Any]:
    return {
        "base_delivery_fee": {
            "split": 0,
            "combined": 0,
            "urgent": 0,
        },
        "area_range": 0,
        "per-pickup-price": 0,
    }


def default_order_payment_rules() -> Dict[str, Any]:
    return {
        "minimum_order_value": {
            "food": 0,
            "grocery": 0,
            "medicine": 0,
            "cross_category": 0,
        },
        "maximum_order_value": {
            "enabled": False,
            "food": 0,
            "grocery": 0,
            "medicine": 0,
            "cross_category": 0,
        },
        "allowed_payment_methods": {
            "upi": True,
            "cards": True,
            "cod": True,
            "net_banking": True,
            "wallet": True,
        },
        "platform_fee": {
            "food": {"mode": "fixed", "value": 0},
            "grocery": {"mode": "fixed", "value": 0},
            "medicine": {"mode": "fixed", "value": 0},
        },
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
    }


def default_misc_settings() -> Dict[str, Any]:
    return {
        "tax_rates": {
            "food_gst_percent": 0,
            "grocery_gst_percent": 0,
            "medicine_gst_percent": 0,
        },
        "tds_settings": {"enabled": False, "percent": 0},
        "service_available": True,
    }


def default_site_configuration_payload() -> Dict[str, Any]:
    return {
        "delivery_fee_settings": default_delivery_fee_settings(),
        "order_payment_rules": default_order_payment_rules(),
        "customer_experience_settings": default_customer_experience_settings(),
        "misc_settings": default_misc_settings(),
    }


def complete_site_configuration_template_payload() -> Dict[str, Any]:
    return default_site_configuration_payload()


class SiteConfiguration(models.Model):
    id = fields.IntField(pk=True)
    delivery_fee_settings = fields.JSONField(default=default_delivery_fee_settings)
    order_payment_rules = fields.JSONField(default=default_order_payment_rules)
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
