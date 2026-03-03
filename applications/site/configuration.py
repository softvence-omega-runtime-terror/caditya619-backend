from decimal import Decimal
from typing import Any, Dict, List

from tortoise import fields, models
from tortoise.exceptions import ValidationError


def default_delivery_fee_settings() -> Dict[str, Any]:
    return {
        "base_delivery_fee": {
            "split": 0.0,
            "combined": 0.0,
            "urgent": 0.0,
        },
        "area_range": 0.0,
        "per-pickup-price": 0.0,
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


def default_refund_settings() -> Dict[str, Any]:
    return {
        "enabled": True,
        "refund_window_days": 7,
        "max_refund_amount": 0.0,
        "support_email": "",
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
        "service_available": True,
        "service_zones": [],
        "blackout_dates": [],
        "festival_holiday_surge_bonus": [],
    }


def default_site_configuration_payload() -> Dict[str, Any]:
    return {
        "delivery_fee_settings": default_delivery_fee_settings(),
        "offers_discount_settings": default_offers_discount_settings(),
        "order_payment_rules": default_order_payment_rules(),
        "customer_experience_settings": default_customer_experience_settings(),
        "refund_settings": default_refund_settings(),
        "misc_settings": default_misc_settings(),
    }


def complete_site_configuration_template_payload() -> Dict[str, Any]:
    payload = default_site_configuration_payload()

    delivery = payload["delivery_fee_settings"]
    delivery["surge_pricing"]["time_slot_rules"] = [
        {
            "name": "Lunch Rush",
            "enabled": False,
            "start": "12:00",
            "end": "14:00",
            "multiplier": 1.0,
        }
    ]
    delivery["surge_pricing"]["festival_rules"] = [
        {
            "name": "Festival Surge",
            "enabled": False,
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
            "multiplier": 1.0,
        }
    ]
    delivery["surge_pricing"]["weather_rules"] = [
        {
            "condition": "rain",
            "enabled": False,
            "multiplier": 1.0,
        }
    ]

    offers = payload["offers_discount_settings"]
    offers["combo_offers"] = [
        {
            "name": "Combo Offer",
            "enabled": False,
            "mode": "percent",
            "value": 0.0,
            "max_cap": 0.0,
            "min_order_value": 0.0,
            "categories": ["food", "grocery"],
        }
    ]

    misc = payload["misc_settings"]
    misc["service_zones"] = [
        {
            "zone_name": "",
            "enabled": False,
            "minimum_order_value": 0.0,
            "delivery_fee": 0.0,
        }
    ]
    misc["blackout_dates"] = [
        {
            "date": "2026-01-01",
            "reason": "",
            "enabled": False,
        }
    ]
    misc["festival_holiday_surge_bonus"] = [
        {
            "name": "Holiday Bonus",
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
            "bonus_percent": 0.0,
            "enabled": False,
        }
    ]

    return payload


class SiteConfiguration(models.Model):
    id = fields.IntField(pk=True)
    delivery_fee_settings = fields.JSONField(default=default_delivery_fee_settings)
    offers_discount_settings = fields.JSONField(default=default_offers_discount_settings)
    order_payment_rules = fields.JSONField(default=default_order_payment_rules)
    customer_experience_settings = fields.JSONField(default=default_customer_experience_settings)
    refund_settings = fields.JSONField(default=default_refund_settings)
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
