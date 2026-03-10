from copy import deepcopy
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


SECTION_ORDER = (
    "delivery_fee_settings",
    "order_payment_rules",
    "customer_experience_settings",
    "misc_settings",
)
SECTION_NAMES = set(SECTION_ORDER)


class SiteConfigurationUpdateSchema(BaseModel):
    delivery_fee_settings: Optional[Dict[str, Any]] = None
    order_payment_rules: Optional[Dict[str, Any]] = None
    customer_experience_settings: Optional[Dict[str, Any]] = None
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
    return {
        "delivery_fee_settings": _sanitize_section(
            "delivery_fee_settings", config.delivery_fee_settings
        ),
        "order_payment_rules": _sanitize_section(
            "order_payment_rules", config.order_payment_rules
        ),
        "customer_experience_settings": _sanitize_section(
            "customer_experience_settings", config.customer_experience_settings
        ),
        "misc_settings": _sanitize_section("misc_settings", config.misc_settings),
    }


async def _get_or_create_site_configuration() -> SiteConfiguration:
    config = await SiteConfiguration.first()
    if config:
        return config

    defaults = default_site_configuration_payload()
    config = await SiteConfiguration.create(
        id=1,
        delivery_fee_settings=_sanitize_section(
            "delivery_fee_settings", defaults["delivery_fee_settings"]
        ),
        order_payment_rules=_sanitize_section(
            "order_payment_rules", defaults["order_payment_rules"]
        ),
        customer_experience_settings=_sanitize_section(
            "customer_experience_settings", defaults["customer_experience_settings"]
        ),
        misc_settings=_sanitize_section("misc_settings", defaults["misc_settings"]),
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


def _filter_by_template(template: Any, value: Any) -> Any:
    if isinstance(template, dict):
        source = value if isinstance(value, dict) else {}
        return {
            key: _filter_by_template(nested_template, source.get(key))
            for key, nested_template in template.items()
        }

    if isinstance(template, list):
        return value if isinstance(value, list) else deepcopy(template)

    return template if value is None else value


def _sanitize_section(section_name: str, value: Any) -> Dict[str, Any]:
    template = default_site_configuration_payload()[section_name]
    source = _normalize_misc_settings(value) if section_name == "misc_settings" else value
    sanitized = _filter_by_template(template, source)
    if section_name == "misc_settings":
        sanitized[SERVICE_AVAILABLE_KEY] = _to_bool(
            sanitized.get(SERVICE_AVAILABLE_KEY),
            default=True,
        )
    return sanitized


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
    return {
        "success": True,
        "data": _serialize_site_configuration(config),
    }



@router.patch("/service-availability/toggle", tags=["Site Configuration"])
async def toggle_service_availability(_: User = Depends(_superuser_guard)):
    config = await _get_or_create_site_configuration()
    updated_misc = _sanitize_section("misc_settings", config.misc_settings)
    current_value = updated_misc[SERVICE_AVAILABLE_KEY]
    next_value = not current_value
    updated_misc[SERVICE_AVAILABLE_KEY] = next_value

    config.misc_settings = updated_misc
    await config.save(update_fields=["misc_settings"])

    return {
        "success": True,
        "data": _serialize_site_configuration(config),
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

    updated_value = _sanitize_section(section_name, updated_value)

    setattr(config, section_name, updated_value)
    await config.save(update_fields=[section_name])

    return {
        "success": True,
        "data": _serialize_site_configuration(config),
    }


@router.post("/reset", tags=["Site Configuration"])
async def reset_site_configuration(_: User = Depends(_superuser_guard)):
    defaults = default_site_configuration_payload()
    config = await _get_or_create_site_configuration()
    for section_name in SECTION_ORDER:
        setattr(config, section_name, _sanitize_section(section_name, defaults[section_name]))
    await config.save()

    return {
        "success": True,
        "data": _serialize_site_configuration(config),
    }
