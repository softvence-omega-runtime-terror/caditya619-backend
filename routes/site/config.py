from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.token import get_current_user
from applications.site.configuration import (
    SiteConfiguration,
    complete_site_configuration_template_payload,
    default_site_configuration_payload,
)
from applications.user.models import User

router = APIRouter(prefix="/configuration")

SERVICE_AVAILABLE_KEY = "service_available"


SECTION_NAMES = {
    "delivery_fee_settings",
    "offers_discount_settings",
    "order_payment_rules",
    "customer_experience_settings",
    "refund_settings",
    "misc_settings",
}


class SiteConfigurationUpdateSchema(BaseModel):
    delivery_fee_settings: Optional[Dict[str, Any]] = None
    offers_discount_settings: Optional[Dict[str, Any]] = None
    order_payment_rules: Optional[Dict[str, Any]] = None
    customer_experience_settings: Optional[Dict[str, Any]] = None
    refund_settings: Optional[Dict[str, Any]] = None
    misc_settings: Optional[Dict[str, Any]] = None


class SectionUpdateSchema(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    merge: bool = Field(
        default=True,
        description="If true, deep-merge into current section. If false, replace section fully.",
    )


async def _superuser_guard(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


def _serialize_site_configuration(config: SiteConfiguration) -> Dict[str, Any]:
    misc_settings = _normalize_misc_settings(config.misc_settings)
    return {
        "id": config.id,
        "delivery_fee_settings": config.delivery_fee_settings,
        "offers_discount_settings": config.offers_discount_settings,
        "order_payment_rules": config.order_payment_rules,
        "customer_experience_settings": config.customer_experience_settings,
        "refund_settings": config.refund_settings,
        "misc_settings": misc_settings,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


async def _get_or_create_site_configuration() -> SiteConfiguration:
    config = await SiteConfiguration.first()
    if config:
        return config

    defaults = default_site_configuration_payload()
    config = await SiteConfiguration.create(
        id=1,
        delivery_fee_settings=defaults["delivery_fee_settings"],
        offers_discount_settings=defaults["offers_discount_settings"],
        order_payment_rules=defaults["order_payment_rules"],
        customer_experience_settings=defaults["customer_experience_settings"],
        refund_settings=defaults["refund_settings"],
        misc_settings=_normalize_misc_settings(defaults["misc_settings"]),
    )
    return config

def _to_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _deep_merge_dicts(current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current)
    for key, value in incoming.items():
        current_value = merged.get(key)
        if isinstance(current_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(current_value, value)
        else:
            merged[key] = value
    return merged


def _normalize_misc_settings(value: Any) -> Dict[str, Any]:
    misc = dict(value) if isinstance(value, dict) else {}
    legacy_value = misc.pop("service_avaliable", None)
    resolved = _to_bool(
        misc.get(SERVICE_AVAILABLE_KEY, legacy_value),
        default=True,
    )
    misc[SERVICE_AVAILABLE_KEY] = resolved
    return misc


@router.get("/template", tags=["Site Configuration"])
async def get_configuration_template(_: User = Depends(_superuser_guard)):
    return {
        "success": True,
        "data": complete_site_configuration_template_payload(),
    }


@router.get("/", tags=["Site Configuration"])
async def get_site_configuration(_: User = Depends(_superuser_guard)):
    config = await _get_or_create_site_configuration()
    return {
        "success": True,
        "data": _serialize_site_configuration(config),
    }


@router.get("/public", tags=["Public Configuration"])
async def get_public_site_configuration():
    config = await _get_or_create_site_configuration()
    customer = config.customer_experience_settings or {}
    order_rules = config.order_payment_rules or {}
    delivery = config.delivery_fee_settings or {}
    offers = config.offers_discount_settings or {}
    misc = _normalize_misc_settings(config.misc_settings)

    return {
        "success": True,
        "data": {
            "support_contact": customer.get("support_contact", {}),
            "grievance_officer": customer.get("grievance_officer", {}),
            "delivery_time_windows": customer.get("delivery_time_windows", {}),
            "allowed_payment_methods": order_rules.get("allowed_payment_methods", {}),
            "minimum_order_value": order_rules.get("minimum_order_value", {}),
            "free_delivery_threshold": delivery.get("free_delivery_threshold", {}),
            "service_available": misc[SERVICE_AVAILABLE_KEY],
            "active_promotional_context": {
                "first_order_discount": offers.get("first_order_discount", {}),
                "weekday_weekend_event_offers": offers.get("weekday_weekend_event_offers", {}),
            },
            "categories_enabled": misc.get("categories_enabled", {}),
            "service_zones": misc.get("service_zones", []),
            "blackout_dates": misc.get("blackout_dates", []),
        },
    }



@router.post("/service-availability/toggle", tags=["Site Configuration"])
async def toggle_service_availability(_: User = Depends(_superuser_guard)):
    config = await _get_or_create_site_configuration()
    updated_misc = _normalize_misc_settings(config.misc_settings)
    current_value = updated_misc[SERVICE_AVAILABLE_KEY]
    next_value = not current_value
    updated_misc[SERVICE_AVAILABLE_KEY] = next_value

    config.misc_settings = updated_misc
    await config.save(update_fields=["misc_settings"])

    return {
        "success": True,
        "message": "Service availability toggled successfully",
        "service_available": updated_misc[SERVICE_AVAILABLE_KEY],
    }




@router.patch("/section/{section_name}", tags=["Site Configuration"])
async def update_configuration_section(
    section_name: str,
    payload: SectionUpdateSchema,
    _: User = Depends(_superuser_guard),
):
    if section_name not in SECTION_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid section '{section_name}'. Allowed sections: {sorted(SECTION_NAMES)}",
        )

    config = await _get_or_create_site_configuration()
    current_value = getattr(config, section_name, None)

    if payload.merge and isinstance(current_value, dict):
        updated_value = _deep_merge_dicts(current_value, payload.data)
    else:
        updated_value = payload.data

    if section_name == "misc_settings":
        updated_value = _normalize_misc_settings(updated_value)

    setattr(config, section_name, updated_value)
    await config.save(update_fields=[section_name])

    return {
        "success": True,
        "message": f"Section '{section_name}' updated successfully",
        "section": section_name,
        "data": updated_value,
    }


@router.post("/reset", tags=["Site Configuration"])
async def reset_site_configuration(_: User = Depends(_superuser_guard)):
    defaults = default_site_configuration_payload()
    config = await _get_or_create_site_configuration()
    for key, value in defaults.items():
        setattr(config, key, value)
    await config.save()

    return {
        "success": True,
        "message": "Site configuration reset to defaults",
        "data": _serialize_site_configuration(config),
    }
