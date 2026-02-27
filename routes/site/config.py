from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.token import get_current_user
from applications.site.configuration import (
    PromoCodeSetting,
    SiteConfiguration,
    default_site_configuration_payload,
)
from applications.user.models import User

router = APIRouter(prefix="/config", tags=["Site Configuration"])


SECTION_NAMES = {
    "delivery_fee_settings",
    "offers_discount_settings",
    "order_payment_rules",
    "vendor_commission_settings",
    "cancellation_refund_policies",
    "customer_experience_settings",
    "misc_settings",
}


class SiteConfigurationUpdateSchema(BaseModel):
    delivery_fee_settings: Optional[Dict[str, Any]] = None
    offers_discount_settings: Optional[Dict[str, Any]] = None
    order_payment_rules: Optional[Dict[str, Any]] = None
    vendor_commission_settings: Optional[Dict[str, Any]] = None
    cancellation_refund_policies: Optional[Dict[str, Any]] = None
    customer_experience_settings: Optional[Dict[str, Any]] = None
    misc_settings: Optional[Dict[str, Any]] = None


class SectionUpdateSchema(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    merge: bool = Field(
        default=True,
        description="If true, shallow-merge into current section. If false, replace section fully.",
    )


class PromoCodeCreateSchema(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    title: Optional[str] = None
    description: Optional[str] = None
    discount_type: str = Field(default="percent")
    discount_value: float = Field(default=0.0, ge=0)
    max_cap: Optional[float] = Field(default=None, ge=0)
    usage_limit: Optional[int] = Field(default=None, ge=1)
    per_user_limit: int = Field(default=1, ge=1)
    min_order_value: float = Field(default=0.0, ge=0)
    applicable_categories: List[str] = Field(default_factory=list)
    is_cross_category: bool = False
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromoCodeUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = Field(default=None, ge=0)
    max_cap: Optional[float] = Field(default=None, ge=0)
    usage_limit: Optional[int] = Field(default=None, ge=1)
    per_user_limit: Optional[int] = Field(default=None, ge=1)
    min_order_value: Optional[float] = Field(default=None, ge=0)
    applicable_categories: Optional[List[str]] = None
    is_cross_category: Optional[bool] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class PromoCodeDisableSchema(BaseModel):
    is_active: bool = False


async def _superuser_guard(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


def _serialize_site_configuration(config: SiteConfiguration) -> Dict[str, Any]:
    return {
        "id": config.id,
        "delivery_fee_settings": config.delivery_fee_settings,
        "offers_discount_settings": config.offers_discount_settings,
        "order_payment_rules": config.order_payment_rules,
        "vendor_commission_settings": config.vendor_commission_settings,
        "cancellation_refund_policies": config.cancellation_refund_policies,
        "customer_experience_settings": config.customer_experience_settings,
        "misc_settings": config.misc_settings,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def _serialize_promo_code(promo: PromoCodeSetting) -> Dict[str, Any]:
    return {
        "id": promo.id,
        "code": promo.code,
        "title": promo.title,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": float(promo.discount_value),
        "max_cap": float(promo.max_cap) if promo.max_cap is not None else None,
        "usage_limit": promo.usage_limit,
        "per_user_limit": promo.per_user_limit,
        "used_count": promo.used_count,
        "min_order_value": float(promo.min_order_value),
        "applicable_categories": promo.applicable_categories,
        "is_cross_category": promo.is_cross_category,
        "starts_at": promo.starts_at.isoformat() if promo.starts_at else None,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "is_active": promo.is_active,
        "metadata": promo.metadata or {},
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
        "updated_at": promo.updated_at.isoformat() if promo.updated_at else None,
    }


def _validate_discount_type(discount_type: str):
    if discount_type not in {"percent", "flat"}:
        raise HTTPException(status_code=422, detail="discount_type must be either 'percent' or 'flat'")


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
        vendor_commission_settings=defaults["vendor_commission_settings"],
        cancellation_refund_policies=defaults["cancellation_refund_policies"],
        customer_experience_settings=defaults["customer_experience_settings"],
        misc_settings=defaults["misc_settings"],
    )
    return config


def _dump_payload(payload: BaseModel) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)  # pydantic v2
    return payload.dict(exclude_none=True)  # pydantic v1 fallback


@router.get("/template")
async def get_configuration_template(_: User = Depends(_superuser_guard)):
    return {
        "success": True,
        "data": default_site_configuration_payload(),
    }


@router.get("/")
async def get_site_configuration(_: User = Depends(_superuser_guard)):
    config = await _get_or_create_site_configuration()
    return {
        "success": True,
        "data": _serialize_site_configuration(config),
    }


@router.get("/public")
async def get_public_site_configuration():
    config = await _get_or_create_site_configuration()
    customer = config.customer_experience_settings or {}
    order_rules = config.order_payment_rules or {}
    delivery = config.delivery_fee_settings or {}
    offers = config.offers_discount_settings or {}
    misc = config.misc_settings or {}

    return {
        "success": True,
        "data": {
            "support_contact": customer.get("support_contact", {}),
            "grievance_officer": customer.get("grievance_officer", {}),
            "delivery_time_windows": customer.get("delivery_time_windows", {}),
            "allowed_payment_methods": order_rules.get("allowed_payment_methods", {}),
            "minimum_order_value": order_rules.get("minimum_order_value", {}),
            "free_delivery_threshold": delivery.get("free_delivery_threshold", {}),
            "active_promotional_context": {
                "first_order_discount": offers.get("first_order_discount", {}),
                "weekday_weekend_event_offers": offers.get("weekday_weekend_event_offers", {}),
            },
            "categories_enabled": misc.get("categories_enabled", {}),
            "service_zones": misc.get("service_zones", []),
            "blackout_dates": misc.get("blackout_dates", []),
        },
    }


@router.put("/")
async def update_site_configuration(
    payload: SiteConfigurationUpdateSchema,
    _: User = Depends(_superuser_guard),
):
    config = await _get_or_create_site_configuration()
    data = _dump_payload(payload)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    for key, value in data.items():
        setattr(config, key, value)

    await config.save()
    return {
        "success": True,
        "message": "Site configuration updated successfully",
        "data": _serialize_site_configuration(config),
    }


@router.patch("/section/{section_name}")
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
        updated_value = {**current_value, **payload.data}
    else:
        updated_value = payload.data

    setattr(config, section_name, updated_value)
    await config.save()

    return {
        "success": True,
        "message": f"Section '{section_name}' updated successfully",
        "section": section_name,
        "data": updated_value,
    }


@router.post("/reset")
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


@router.post("/promo-codes")
async def create_promo_code(
    payload: PromoCodeCreateSchema,
    _: User = Depends(_superuser_guard),
):
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="Promo code cannot be empty")
    _validate_discount_type(payload.discount_type)

    existing = await PromoCodeSetting.get_or_none(code=code)
    if existing:
        raise HTTPException(status_code=409, detail="Promo code already exists")

    promo = await PromoCodeSetting.create(
        code=code,
        title=payload.title,
        description=payload.description,
        discount_type=payload.discount_type,
        discount_value=Decimal(str(payload.discount_value)),
        max_cap=Decimal(str(payload.max_cap)) if payload.max_cap is not None else None,
        usage_limit=payload.usage_limit,
        per_user_limit=payload.per_user_limit,
        min_order_value=Decimal(str(payload.min_order_value)),
        applicable_categories=payload.applicable_categories,
        is_cross_category=payload.is_cross_category,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        is_active=payload.is_active,
        metadata=payload.metadata,
    )

    return {
        "success": True,
        "message": "Promo code created successfully",
        "data": _serialize_promo_code(promo),
    }


@router.get("/promo-codes")
async def list_promo_codes(
    active_only: bool = False,
    _: User = Depends(_superuser_guard),
):
    query = PromoCodeSetting.all().order_by("-created_at")
    if active_only:
        query = query.filter(is_active=True)

    promos = await query
    return {
        "success": True,
        "count": len(promos),
        "data": [_serialize_promo_code(promo) for promo in promos],
    }


@router.get("/promo-codes/{promo_id}")
async def get_promo_code(
    promo_id: int,
    _: User = Depends(_superuser_guard),
):
    promo = await PromoCodeSetting.get_or_none(id=promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    return {
        "success": True,
        "data": _serialize_promo_code(promo),
    }


@router.patch("/promo-codes/{promo_id}")
async def update_promo_code(
    promo_id: int,
    payload: PromoCodeUpdateSchema,
    _: User = Depends(_superuser_guard),
):
    promo = await PromoCodeSetting.get_or_none(id=promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    data = _dump_payload(payload)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    if "discount_type" in data:
        _validate_discount_type(data["discount_type"])

    decimal_fields = {"discount_value", "max_cap", "min_order_value"}
    for key, value in data.items():
        if key in decimal_fields and value is not None:
            setattr(promo, key, Decimal(str(value)))
        else:
            setattr(promo, key, value)

    await promo.save()
    return {
        "success": True,
        "message": "Promo code updated successfully",
        "data": _serialize_promo_code(promo),
    }


@router.post("/promo-codes/{promo_id}/disable")
async def disable_promo_code(
    promo_id: int,
    payload: PromoCodeDisableSchema,
    _: User = Depends(_superuser_guard),
):
    promo = await PromoCodeSetting.get_or_none(id=promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    promo.is_active = payload.is_active
    await promo.save(update_fields=["is_active", "updated_at"])

    return {
        "success": True,
        "message": "Promo code status updated successfully",
        "data": _serialize_promo_code(promo),
    }


@router.delete("/promo-codes/{promo_id}")
async def delete_promo_code(
    promo_id: int,
    _: User = Depends(_superuser_guard),
):
    promo = await PromoCodeSetting.get_or_none(id=promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    await promo.delete()
    return {
        "success": True,
        "message": "Promo code deleted successfully",
    }
