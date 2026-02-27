from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import settings
from applications.customer.models import Order, OrderStatus
from applications.items.models import Item

router = APIRouter(prefix="/restaurant", tags=["PetPooja Restaurant"])
templates = Jinja2Templates(directory="templates")


PETPOOJA_ENDPOINTS = {
    "fetch_menu": "PETPOOJA_FETCH_MENU_URL",
    "save_order": "PETPOOJA_SAVE_ORDER_URL",
    "update_order_status": "PETPOOJA_UPDATE_ORDER_STATUS_URL",
    "rider_status_update": "PETPOOJA_RIDER_STATUS_UPDATE_URL",
    "get_store_status": "PETPOOJA_GET_STORE_STATUS_URL",
    "update_store_status": "PETPOOJA_UPDATE_STORE_STATUS_URL",
}


class PetPoojaAuthMixin(BaseModel):
    app_key: Optional[str] = Field(default=None)
    app_secret: Optional[str] = Field(default=None)
    access_token: Optional[str] = Field(default=None)


class FetchMenuRequest(PetPoojaAuthMixin):
    restID: str = Field(..., min_length=1, description="Unique restaurant mapping id")


class SelectRestaurantRequest(BaseModel):
    restID: str = Field(..., min_length=1, description="Unique restaurant mapping id")


class FetchRestaurantsRequest(PetPoojaAuthMixin):
    restID: Optional[str] = Field(
        default=None,
        description="Optional unique restaurant mapping id. If omitted, provider may return all mapped restaurants.",
    )


class PetPoojaActionRequest(PetPoojaAuthMixin):
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw payload that will be forwarded to PetPooja endpoint with credentials.",
    )


class CredentialsValidationRequest(PetPoojaAuthMixin):
    restID: str = Field(..., min_length=1, description="Mapped restaurant id for validation test")


def _clean_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on", "instock"}:
            return True
        if v in {"0", "false", "no", "n", "off", "outofstock"}:
            return False
    return None


def _get_credentials(
    app_key: Optional[str] = None,
    app_secret: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Dict[str, str]:
    return {
        "app_key": _clean_string(app_key) or _clean_string(settings.PETPOOJA_APP_KEY) or "",
        "app_secret": _clean_string(app_secret) or _clean_string(settings.PETPOOJA_APP_SECRET) or "",
        "access_token": _clean_string(access_token) or _clean_string(settings.PETPOOJA_ACCESS_TOKEN) or "",
    }


def _require_credentials(credentials: Dict[str, str]):
    missing = [k for k, v in credentials.items() if not v]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing PetPooja credentials",
                "missing_fields": missing,
            },
        )


def _get_petpooja_url(action: str) -> str:
    setting_key = PETPOOJA_ENDPOINTS.get(action)
    if not setting_key:
        raise HTTPException(status_code=500, detail=f"Unsupported PetPooja action: {action}")

    url = getattr(settings, setting_key, "")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(
            status_code=500,
            detail=f"Missing configuration for PetPooja action '{action}' ({setting_key})",
        )
    return url.strip()


def _merge_auth_payload(
    payload: Dict[str, Any],
    credentials: Dict[str, str],
    include_empty_credentials: bool = False,
) -> Dict[str, Any]:
    body = dict(payload or {})
    for key, value in credentials.items():
        if value or include_empty_credentials:
            body[key] = value
    return body


def _validate_required_fields(payload: Dict[str, Any], required_fields: List[str], action_name: str):
    missing = []
    for field_name in required_fields:
        value = payload.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Missing required fields for {action_name}",
                "missing_fields": missing,
            },
        )


async def _post_to_petpooja(action: str, payload: Dict[str, Any], auth: PetPoojaAuthMixin) -> Dict[str, Any]:
    url = _get_petpooja_url(action)
    credentials = _get_credentials(
        app_key=auth.app_key,
        app_secret=auth.app_secret,
        access_token=auth.access_token,
    )
    _require_credentials(credentials)
    body = _merge_auth_payload(payload, credentials)

    try:
        async with httpx.AsyncClient(timeout=settings.PETPOOJA_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=body)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"PetPooja '{action}' request timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach PetPooja '{action}' endpoint: {exc}")

    try:
        response_data: Any = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": f"PetPooja '{action}' request failed",
                "petpooja_response": response_data,
            },
        )

    if isinstance(response_data, dict):
        success = response_data.get("success")
        status = response_data.get("status")
        if str(success).lower() in {"0", "false"} or str(status).strip().lower() == "failed":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"PetPooja '{action}' rejected request",
                    "petpooja_response": response_data,
                },
            )
        return response_data

    return {"data": response_data}


def _extract_restaurant_summary(menu_data: Dict[str, Any], rest_id: str) -> Dict[str, Any]:
    restaurants = menu_data.get("restaurants")
    restaurant: Dict[str, Any] = {}

    if isinstance(restaurants, list) and restaurants:
        first_restaurant = restaurants[0]
        if isinstance(first_restaurant, dict):
            restaurant = first_restaurant

    name = (
        restaurant.get("restaurantname")
        or restaurant.get("restaurant_name")
        or restaurant.get("res_name")
        or restaurant.get("name")
    )

    mapped_rest_id = (
        restaurant.get("restID")
        or restaurant.get("restid")
        or restaurant.get("restaurantid")
        or rest_id
    )

    return {
        "restID": str(mapped_rest_id),
        "name": name or f"Restaurant {rest_id}",
        "raw": restaurant,
    }


def _extract_restaurant_list(menu_data: Dict[str, Any], fallback_rest_id: Optional[str] = None) -> List[Dict[str, Any]]:
    restaurants_raw = menu_data.get("restaurants")
    restaurant_list: List[Dict[str, Any]] = []

    if isinstance(restaurants_raw, list):
        for idx, row in enumerate(restaurants_raw):
            if not isinstance(row, dict):
                continue

            row_rest_id = (
                row.get("restID")
                or row.get("restid")
                or row.get("restaurantid")
                or row.get("id")
                or fallback_rest_id
                or f"restaurant-{idx + 1}"
            )
            row_name = (
                row.get("restaurantname")
                or row.get("restaurant_name")
                or row.get("res_name")
                or row.get("name")
                or f"Restaurant {row_rest_id}"
            )
            restaurant_list.append(
                {
                    "restID": str(row_rest_id),
                    "name": row_name,
                    "raw": row,
                }
            )

    if not restaurant_list and fallback_rest_id:
        restaurant_list.append(_extract_restaurant_summary(menu_data, fallback_rest_id))

    return restaurant_list


def _extract_menu_preview(menu_data: Dict[str, Any], sample_size: int = 10) -> Dict[str, Any]:
    categories = menu_data.get("categories")
    items = menu_data.get("items")

    category_count = len(categories) if isinstance(categories, list) else 0
    item_count = len(items) if isinstance(items, list) else 0

    sample_items: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for item in items[:sample_size]:
            if not isinstance(item, dict):
                continue
            sample_items.append(
                {
                    "item_id": item.get("itemid") or item.get("id"),
                    "name": item.get("itemname") or item.get("name"),
                    "price": item.get("price") or item.get("item_price") or item.get("saleprice"),
                    "in_stock": item.get("in_stock") if "in_stock" in item else item.get("instock"),
                    "category_id": item.get("categoryid") or item.get("category_id"),
                }
            )

    return {
        "category_count": category_count,
        "item_count": item_count,
        "sample_items": sample_items,
    }


def _map_petpooja_status(raw_status: Any) -> Optional[OrderStatus]:
    if raw_status is None:
        return None

    normalized = str(raw_status).strip().lower().replace(" ", "_")
    normalized = normalized.replace("-", "_")

    status_map = {
        "-1": OrderStatus.CANCELLED,
        "cancelled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.CANCELLED,
        "0": OrderStatus.PENDING,
        "pending": OrderStatus.PENDING,
        "1": OrderStatus.CONFIRMED,
        "accepted": OrderStatus.CONFIRMED,
        "confirmed": OrderStatus.CONFIRMED,
        "2": OrderStatus.PREPARED,
        "prepared": OrderStatus.PREPARED,
        "ready": OrderStatus.PREPARED,
        "food_ready": OrderStatus.PREPARED,
        "3": OrderStatus.OUT_FOR_DELIVERY,
        "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
        "pickedup": OrderStatus.OUT_FOR_DELIVERY,
        "picked_up": OrderStatus.OUT_FOR_DELIVERY,
        "4": OrderStatus.DELIVERED,
        "delivered": OrderStatus.DELIVERED,
        "rider_assigned": OrderStatus.SHIPPED,
        "rider_arrived": OrderStatus.PREPARED,
    }
    return status_map.get(normalized)


def _extract_internal_order_ref(payload: Dict[str, Any]) -> Optional[str]:
    candidate_keys = [
        "internal_order_id",
        "clientorderID",
        "client_order_id",
        "order_id",
        "orderID",
        "tracking_number",
    ]
    for key in candidate_keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _verify_callback_credentials(payload: Dict[str, Any]):
    if not settings.PETPOOJA_VERIFY_CALLBACK_CREDENTIALS:
        return

    configured = _get_credentials()
    incoming = {
        "app_key": _clean_string(str(payload.get("app_key", ""))) or "",
        "app_secret": _clean_string(str(payload.get("app_secret", ""))) or "",
        "access_token": _clean_string(str(payload.get("access_token", ""))) or "",
    }
    if incoming != configured:
        raise HTTPException(status_code=401, detail="Invalid PetPooja callback credentials")


async def _sync_internal_order_from_callback(payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    order_ref = _extract_internal_order_ref(payload)
    if not order_ref:
        return {
            "updated": False,
            "reason": "No internal order reference found in payload",
        }

    order = await Order.get_or_none(id=order_ref)
    if not order:
        order = await Order.get_or_none(tracking_number=order_ref)
    if not order:
        order = await Order.get_or_none(cf_order_id=order_ref)
    if not order:
        return {
            "updated": False,
            "reason": f"Order not found for reference '{order_ref}'",
        }

    metadata = order.metadata or {}
    events = metadata.get("petpooja_events", [])
    if not isinstance(events, list):
        events = []
    events.append(
        {
            "source": source,
            "received_at": _utc_now_iso(),
            "payload": payload,
        }
    )
    metadata["petpooja_events"] = events[-50:]

    petpooja_order_id = payload.get("orderID") or payload.get("external_order_id")
    if petpooja_order_id:
        metadata["petpooja_order_id"] = str(petpooja_order_id)

    mapped_status = _map_petpooja_status(payload.get("status"))

    fields_to_update = ["metadata"]
    order.metadata = metadata

    if mapped_status and order.status != mapped_status:
        order.status = mapped_status
        fields_to_update.append("status")

    cancel_reason = payload.get("cancelReason")
    if cancel_reason:
        order.reason = str(cancel_reason)
        fields_to_update.append("reason")

    await order.save(update_fields=list(dict.fromkeys(fields_to_update)))

    return {
        "updated": True,
        "order_id": order.id,
        "mapped_status": mapped_status.value if mapped_status else None,
    }


async def _apply_item_stock_update(payload: Dict[str, Any], forced_in_stock: Optional[bool] = None) -> Dict[str, Any]:
    in_stock = forced_in_stock
    if in_stock is None:
        in_stock = _coerce_bool(payload.get("inStock"))
    if in_stock is None:
        raise HTTPException(status_code=422, detail="Missing or invalid inStock value")

    raw_item_ids = payload.get("itemID") or payload.get("itemIds") or payload.get("item_ids")
    if raw_item_ids is None:
        raise HTTPException(status_code=422, detail="Missing itemID list")

    if not isinstance(raw_item_ids, list):
        raw_item_ids = [raw_item_ids]

    item_ids: List[int] = []
    for value in raw_item_ids:
        try:
            item_ids.append(int(value))
        except (TypeError, ValueError):
            continue

    if not item_ids:
        raise HTTPException(status_code=422, detail="No valid integer item IDs in payload")

    updated_count = await Item.filter(id__in=item_ids).update(is_stock=in_stock)
    return {
        "requested_item_ids": item_ids,
        "updated_count": updated_count,
        "in_stock": in_stock,
    }


@router.get("/health")
async def petpooja_health():
    credentials = _get_credentials()
    return {
        "success": True,
        "credentials_configured": {key: bool(value) for key, value in credentials.items()},
        "endpoint_configured": {
            action: bool(_clean_string(getattr(settings, setting_key, "")))
            for action, setting_key in PETPOOJA_ENDPOINTS.items()
        },
    }


@router.post("/credentials/validate")
async def validate_petpooja_credentials(payload: CredentialsValidationRequest):
    body = {"restID": payload.restID.strip()}
    data = await _post_to_petpooja("fetch_menu", body, payload)
    return {
        "success": True,
        "message": "PetPooja credentials validated successfully",
        "data": data,
    }


@router.post("/fetch-menu")
async def fetch_menu(payload: FetchMenuRequest):
    body = {"restID": payload.restID.strip()}
    menu_data = await _post_to_petpooja("fetch_menu", body, payload)
    return {
        "success": True,
        "restID": payload.restID,
        "data": menu_data,
    }


@router.post("/select")
async def select_restaurant(payload: SelectRestaurantRequest):
    auth = FetchMenuRequest(restID=payload.restID)
    menu_data = await _post_to_petpooja("fetch_menu", {"restID": payload.restID.strip()}, auth)
    restaurant = _extract_restaurant_summary(menu_data, payload.restID)
    modal_data = _extract_menu_preview(menu_data)

    return {
        "success": True,
        "message": "Restaurant selected successfully",
        "restaurant": restaurant,
        "modal": {
            "title": restaurant["name"],
            "subtitle": f"restID: {restaurant['restID']}",
            **modal_data,
        },
        "menu": menu_data,
    }


@router.post("/fetch-restaurants")
async def fetch_restaurants(payload: FetchRestaurantsRequest):
    body: Dict[str, Any] = {}
    rest_id = _clean_string(payload.restID)
    if rest_id:
        body["restID"] = rest_id

    menu_data = await _post_to_petpooja("fetch_menu", body, payload)
    restaurants = _extract_restaurant_list(menu_data, fallback_rest_id=rest_id)

    return {
        "success": True,
        "message": "PetPooja restaurants fetched successfully",
        "count": len(restaurants),
        "restaurants": restaurants,
        "data": menu_data,
    }


@router.get("/restaurants")
async def get_restaurants(
    restID: Optional[str] = Query(default=None),
    app_key: Optional[str] = Query(default=None),
    app_secret: Optional[str] = Query(default=None),
    access_token: Optional[str] = Query(default=None),
):
    payload = FetchRestaurantsRequest(
        restID=restID,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
    )
    return await fetch_restaurants(payload)


@router.post("/save-order")
async def save_order(payload: PetPoojaActionRequest):
    body = dict(payload.payload or {})
    _validate_required_fields(body, ["restID"], "save-order")
    response_data = await _post_to_petpooja("save_order", body, payload)
    return {
        "success": True,
        "message": "Order sent to PetPooja successfully",
        "data": response_data,
    }


@router.post("/update-order-status")
async def update_order_status(payload: PetPoojaActionRequest):
    body = dict(payload.payload or {})
    _validate_required_fields(body, ["restID", "clientorderID", "status"], "update-order-status")
    response_data = await _post_to_petpooja("update_order_status", body, payload)
    return {
        "success": True,
        "message": "Order status update sent to PetPooja successfully",
        "data": response_data,
    }


@router.post("/rider-status-update")
async def rider_status_update(payload: PetPoojaActionRequest):
    body = dict(payload.payload or {})
    _validate_required_fields(body, ["order_id", "status"], "rider-status-update")
    response_data = await _post_to_petpooja("rider_status_update", body, payload)
    return {
        "success": True,
        "message": "Rider status sent to PetPooja successfully",
        "data": response_data,
    }


@router.post("/get-store-status")
async def get_store_status(payload: PetPoojaActionRequest):
    body = dict(payload.payload or {})
    _validate_required_fields(body, ["restID"], "get-store-status")
    response_data = await _post_to_petpooja("get_store_status", body, payload)
    return {
        "success": True,
        "message": "Store status fetched successfully",
        "data": response_data,
    }


@router.post("/update-store-status")
async def update_store_status(payload: PetPoojaActionRequest):
    body = dict(payload.payload or {})
    _validate_required_fields(body, ["restID", "store_status"], "update-store-status")
    response_data = await _post_to_petpooja("update_store_status", body, payload)
    return {
        "success": True,
        "message": "Store status updated successfully",
        "data": response_data,
    }


@router.post("/webhook/push-menu")
async def push_menu_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    menu_preview = _extract_menu_preview(payload)
    return {
        "success": True,
        "message": "Push menu webhook received",
        "received_at": _utc_now_iso(),
        "preview": menu_preview,
    }


@router.post("/webhook/order-callback")
async def order_callback_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    sync_info = await _sync_internal_order_from_callback(payload, source="order-callback")
    return {
        "success": True,
        "message": "Order callback received",
        "sync": sync_info,
    }


@router.post("/webhook/rider-info")
async def rider_info_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    sync_info = await _sync_internal_order_from_callback(payload, source="rider-info")
    return {
        "success": True,
        "message": "Rider info webhook received",
        "sync": sync_info,
    }


@router.post("/webhook/item-stock")
async def item_stock_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    stock_result = await _apply_item_stock_update(payload)
    return {
        "success": True,
        "message": "Item stock webhook processed",
        "result": stock_result,
    }


@router.post("/webhook/item-stock/in")
async def item_stock_in_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    stock_result = await _apply_item_stock_update(payload, forced_in_stock=True)
    return {
        "success": True,
        "message": "In-stock webhook processed",
        "result": stock_result,
    }


@router.post("/webhook/item-stock/out")
async def item_stock_out_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    stock_result = await _apply_item_stock_update(payload, forced_in_stock=False)
    return {
        "success": True,
        "message": "Out-of-stock webhook processed",
        "result": stock_result,
    }


@router.post("/webhook/store-status")
async def store_status_webhook(payload: Dict[str, Any]):
    _verify_callback_credentials(payload)
    sync_info = await _sync_internal_order_from_callback(payload, source="store-status")
    return {
        "success": True,
        "message": "Store status webhook received",
        "sync": sync_info,
        "received_at": _utc_now_iso(),
    }


@router.get("/modal", response_class=HTMLResponse)
async def restaurant_modal_page(request: Request):
    return templates.TemplateResponse(
        "petpuja_restaurant_modal.html",
        {
            "request": request,
            "fetch_menu_url": settings.PETPOOJA_FETCH_MENU_URL,
            "fetch_restaurants_url": "/petpuja/restaurant/restaurants",
        },
    )
