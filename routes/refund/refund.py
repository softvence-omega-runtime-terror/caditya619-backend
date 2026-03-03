import logging
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.token import get_current_user
from applications.customer.models import Order, OrderStatus
from applications.payment.models import Refund, RefundLog
from applications.user.models import User

router = APIRouter(tags=["Refund System"])
logger = logging.getLogger(__name__)

CASHFREE_API_VERSION = "2023-08-01"


class RefundCreateSchema(BaseModel):
    order_reference: str = Field(..., min_length=1, max_length=255)
    refund_amount: Optional[Decimal] = Field(default=None, gt=0)
    reason: str = Field(default="customer_request", max_length=100)
    note: str = Field(default="Customer requested refund", max_length=255)


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_order_status_text(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _payment_method_text(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).lower()
    return str(value or "").lower()


def _cashfree_base_url() -> str:
    env = str(settings.CASHFREE_ENV or "PRODUCTION").upper()
    if env in {"SANDBOX", "TEST"}:
        return "https://sandbox.cashfree.com/pg"
    return "https://api.cashfree.com/pg"


def _cashfree_headers() -> Dict[str, str]:
    if not settings.CASHFREE_CLIENT_PAYMENT_ID or not settings.CASHFREE_CLIENT_PAYMENT_SECRET:
        raise HTTPException(status_code=500, detail="Cashfree credentials are not configured")
    return {
        "x-client-id": settings.CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": settings.CASHFREE_CLIENT_PAYMENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json",
    }


def _extract_gateway_refund_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ("cf_refund_id", "gateway_refund_id", "refund_id"):
        value = payload.get(key)
        if value:
            return str(value)
    nested = payload.get("refund")
    if isinstance(nested, dict):
        for key in ("cf_refund_id", "gateway_refund_id", "refund_id"):
            value = nested.get(key)
            if value:
                return str(value)
    return None


def _map_cashfree_refund_status(value: Any) -> str:
    status = str(value or "").upper()
    if status in {"SUCCESS", "COMPLETED"}:
        return "completed"
    if status in {"FAILED", "CANCELLED", "REJECTED"}:
        return "failed"
    return "processing"


def _serialize_refund(refund: Refund) -> Dict[str, Any]:
    return {
        "id": refund.id,
        "order_id": refund.order_id,
        "user_id": refund.user_id,
        "refund_amount": float(refund.refund_amount),
        "cancellation_fee": float(refund.cancellation_fee),
        "original_amount": float(refund.original_amount),
        "status": refund.status,
        "reason": refund.reason,
        "payment_method": refund.payment_method,
        "gateway_refund_id": refund.gateway_refund_id,
        "expected_completion": refund.expected_completion.isoformat() if refund.expected_completion else None,
        "completed_at": refund.completed_at.isoformat() if refund.completed_at else None,
        "created_at": refund.created_at.isoformat() if refund.created_at else None,
    }


async def _log_refund_event(
    refund_id: str,
    order_id: str,
    action: str,
    old_status: Optional[str],
    new_status: Optional[str],
    actor_type: str,
    error: Optional[str] = None,
) -> None:
    try:
        await RefundLog.create(
            refund_id=refund_id,
            order_id=order_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            actor_type=actor_type,
            error=error,
        )
    except Exception as exc:
        logger.warning("RefundLog create failed for %s: %s", refund_id, exc)


async def _load_orders_for_reference(order_reference: str, current_user: User) -> Tuple[List[Order], str]:
    ref = order_reference.strip()
    if not ref:
        raise HTTPException(status_code=422, detail="order_reference is required")

    filters: Dict[str, Any] = {}
    if not current_user.is_superuser:
        filters["user_id"] = current_user.id

    orders = await Order.filter(parent_order_id=ref, **filters).all()
    normalized_ref = ref
    if orders:
        return orders, normalized_ref

    primary = await Order.get_or_none(id=ref, **filters)
    if not primary:
        raise HTTPException(status_code=404, detail="Order not found")

    parent_ref = primary.parent_order_id
    if parent_ref:
        grouped = await Order.filter(parent_order_id=parent_ref, **filters).all()
        if grouped:
            return grouped, parent_ref

    return [primary], primary.id


async def _cashfree_create_refund(
    cashfree_order_id: str,
    refund_id: str,
    refund_amount: Decimal,
    refund_note: str,
) -> Tuple[bool, Any]:
    url = f"{_cashfree_base_url()}/orders/{cashfree_order_id}/refunds"
    payload = {
        "refund_id": refund_id,
        "refund_amount": float(refund_amount),
        "refund_note": refund_note,
        "refund_speed": "STANDARD",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=_cashfree_headers())

    data: Any
    try:
        data = response.json()
    except Exception:
        data = response.text

    if response.status_code in {200, 201, 202}:
        return True, data
    return False, data


async def _cashfree_fetch_refund(cashfree_order_id: str, refund_id: str) -> Tuple[bool, Any]:
    url = f"{_cashfree_base_url()}/orders/{cashfree_order_id}/refunds/{refund_id}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_cashfree_headers())

    try:
        data: Any = response.json()
    except Exception:
        data = response.text

    if response.status_code == 200:
        return True, data
    return False, data


@router.post("/request", response_model=dict)
async def create_refund_request(
    payload: RefundCreateSchema,
    current_user: User = Depends(get_current_user),
):
    orders, normalized_order_ref = await _load_orders_for_reference(payload.order_reference, current_user)

    payment_methods = {_payment_method_text(order.payment_method) for order in orders}
    if payment_methods != {"cashfree"}:
        raise HTTPException(status_code=400, detail="Only Cashfree paid orders are supported for refund")

    unpaid_orders = [order.id for order in orders if str(order.payment_status or "").lower() != "paid"]
    if unpaid_orders:
        raise HTTPException(
            status_code=400,
            detail=f"Refund allowed only for paid orders. Unpaid: {unpaid_orders}",
        )

    active_refund = await Refund.filter(
        order_id=normalized_order_ref,
        status__in=["initiated", "processing"],
    ).order_by("-created_at").first()
    if active_refund:
        raise HTTPException(
            status_code=409,
            detail=f"Active refund already exists for this order ({active_refund.id})",
        )

    original_amount = sum((_to_decimal(order.total) for order in orders), Decimal("0.00"))
    requested_amount = payload.refund_amount if payload.refund_amount is not None else original_amount
    requested_amount = _to_decimal(requested_amount)

    if requested_amount <= 0:
        raise HTTPException(status_code=422, detail="Refund amount must be greater than zero")
    if requested_amount > original_amount:
        raise HTTPException(
            status_code=422,
            detail=f"Refund amount {requested_amount} cannot exceed original amount {original_amount}",
        )

    refund_id = f"REF_{uuid.uuid4().hex[:12].upper()}"
    refund = await Refund.create(
        id=refund_id,
        order_id=normalized_order_ref,
        user_id=orders[0].user_id,
        refund_amount=requested_amount,
        cancellation_fee=Decimal("0.00"),
        original_amount=original_amount,
        status="initiated",
        reason=payload.reason,
        payment_method="cashfree",
        expected_completion=datetime.utcnow(),
    )
    await _log_refund_event(refund.id, refund.order_id, "initiated", None, "initiated", "customer")

    cashfree_order_id = str(orders[0].payment_id or normalized_order_ref)
    success, cf_data = await _cashfree_create_refund(
        cashfree_order_id=cashfree_order_id,
        refund_id=refund.id,
        refund_amount=requested_amount,
        refund_note=payload.note,
    )

    if not success:
        old_status = refund.status
        refund.status = "failed"
        await refund.save(update_fields=["status"])
        await _log_refund_event(
            refund.id,
            refund.order_id,
            "failed",
            old_status,
            refund.status,
            "gateway",
            error=str(cf_data),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Cashfree refund creation failed",
                "refund_id": refund.id,
                "cashfree_error": cf_data,
            },
        )

    gateway_refund_id = _extract_gateway_refund_id(cf_data)
    old_status = refund.status
    refund.status = "processing"
    update_fields = ["status"]
    if gateway_refund_id:
        refund.gateway_refund_id = gateway_refund_id
        update_fields.append("gateway_refund_id")
    await refund.save(update_fields=update_fields)
    await _log_refund_event(refund.id, refund.order_id, "processing", old_status, refund.status, "gateway")

    for order in orders:
        if _to_order_status_text(order.status) != OrderStatus.REFUND_REQUESTED.value:
            order.status = OrderStatus.REFUND_REQUESTED
            await order.save(update_fields=["status"])

    return {
        "success": True,
        "message": "Refund initiated successfully",
        "cashfree_order_id": cashfree_order_id,
        "refund": _serialize_refund(refund),
        "cashfree_response": cf_data,
    }


@router.get("/", response_model=List[dict])
async def list_refunds(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    query = Refund.all().order_by("-created_at") if current_user.is_superuser else Refund.filter(user_id=current_user.id).order_by("-created_at")
    if status:
        query = query.filter(status=status)
    refunds = await query
    return [_serialize_refund(refund) for refund in refunds]


@router.get("/order/{order_reference}", response_model=List[dict])
async def list_refunds_by_order(
    order_reference: str,
    current_user: User = Depends(get_current_user),
):
    orders, normalized_order_ref = await _load_orders_for_reference(order_reference, current_user)
    candidate_keys = {normalized_order_ref, order_reference}
    candidate_keys.update({order.id for order in orders})
    candidate_keys.update({order.parent_order_id for order in orders if order.parent_order_id})

    refunds = await Refund.filter(order_id__in=[key for key in candidate_keys if key]).order_by("-created_at")
    return [_serialize_refund(refund) for refund in refunds]


@router.get("/{refund_id}", response_model=dict)
async def get_refund_detail(
    refund_id: str,
    current_user: User = Depends(get_current_user),
):
    refund = await Refund.get_or_none(id=refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    if not current_user.is_superuser and refund.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this refund")

    return {
        "success": True,
        "refund": _serialize_refund(refund),
    }


@router.post("/{refund_id}/sync", response_model=dict)
async def sync_refund_status(
    refund_id: str,
    current_user: User = Depends(get_current_user),
):
    refund = await Refund.get_or_none(id=refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    if not current_user.is_superuser and refund.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to sync this refund")

    anchor_order = await Order.filter(parent_order_id=refund.order_id).first()
    if not anchor_order:
        anchor_order = await Order.get_or_none(id=refund.order_id)
    cashfree_order_id = str(anchor_order.payment_id) if anchor_order and anchor_order.payment_id else refund.order_id

    success, cf_data = await _cashfree_fetch_refund(cashfree_order_id, refund.id)
    if not success:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to fetch refund status from Cashfree",
                "cashfree_error": cf_data,
            },
        )

    raw_status = None
    if isinstance(cf_data, dict):
        raw_status = (
            cf_data.get("refund_status")
            or cf_data.get("status")
            or (cf_data.get("refund") or {}).get("refund_status")
            or (cf_data.get("refund") or {}).get("status")
        )
    mapped_status = _map_cashfree_refund_status(raw_status)
    gateway_refund_id = _extract_gateway_refund_id(cf_data)

    old_status = refund.status
    update_fields: List[str] = []
    if mapped_status != refund.status:
        refund.status = mapped_status
        update_fields.append("status")
    if gateway_refund_id and gateway_refund_id != refund.gateway_refund_id:
        refund.gateway_refund_id = gateway_refund_id
        update_fields.append("gateway_refund_id")
    if mapped_status == "completed" and not refund.completed_at:
        refund.completed_at = datetime.utcnow()
        update_fields.append("completed_at")

    if update_fields:
        await refund.save(update_fields=update_fields)

    if old_status != refund.status:
        await _log_refund_event(refund.id, refund.order_id, "status_sync", old_status, refund.status, "gateway")

    if mapped_status in {"processing", "completed"}:
        orders = await Order.filter(parent_order_id=refund.order_id).all()
        if not orders:
            order = await Order.get_or_none(id=refund.order_id)
            orders = [order] if order else []
        target_status = OrderStatus.REFUND_APPROVED if mapped_status == "processing" else OrderStatus.REFUNDED
        for order in orders:
            if order and _to_order_status_text(order.status) != target_status.value:
                order.status = target_status
                await order.save(update_fields=["status"])

    return {
        "success": True,
        "message": "Refund status synced",
        "cashfree_order_id": cashfree_order_id,
        "refund": _serialize_refund(refund),
        "cashfree_response": cf_data,
    }
