# ============================================================
# REFUND SYSTEM - SIMPLE VERSION
# One file: refund.py
# ============================================================

import logging
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException
from tortoise import fields
from tortoise.models import Model
from pydantic import BaseModel
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/refunds", tags=["refunds"])

# ============================================================
# DATABASE MODELS
# ============================================================

class Refund(Model):
    """Refund tracking"""
    id = fields.CharField(max_length=255, pk=True)
    order_id = fields.CharField(max_length=255, index=True)
    user_id = fields.IntField(index=True)
    
    refund_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    cancellation_fee = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
    original_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    
    status = fields.CharField(max_length=50, default="initiated", index=True)
    reason = fields.CharField(max_length=100, default="customer_cancellation")
    
    payment_method = fields.CharField(max_length=50, null=True)
    gateway_refund_id = fields.CharField(max_length=255, null=True, unique=True)
    
    expected_completion = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "refunds"


class RefundLog(Model):
    """Audit trail"""
    refund_id = fields.CharField(max_length=255, index=True)
    order_id = fields.CharField(max_length=255)
    action = fields.CharField(max_length=100)
    old_status = fields.CharField(max_length=50, null=True)
    new_status = fields.CharField(max_length=50, null=True)
    actor_type = fields.CharField(max_length=50)  # customer, gateway, system
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "refund_logs"


# ============================================================
# SCHEMAS
# ============================================================

class CancelCheckResponse(BaseModel):
    can_cancel: bool
    refund_amount: float
    cancellation_fee: float
    reason: str
    expected_by: str


class CancelOrderResponse(BaseModel):
    success: bool
    refund_id: str
    status: str
    refund_amount: float
    cancellation_fee: float


class RefundStatusResponse(BaseModel):
    refund_id: str
    status: str
    refund_amount: float
    completed_at: str = None


# ============================================================
# HELPERS
# ============================================================

async def get_order(order_id: str):
    """Get order - replace with your actual import"""
    from applications.customer.models import Order
    return await Order.get_or_none(id=order_id)


def can_cancel(status: str) -> bool:
    """Check if order status allows cancellation"""
    blocked = ["shipped", "out_for_delivery", "delivered", "cancelled"]
    return status.lower() not in blocked


def get_fee(status: str, amount: float) -> float:
    """Calculate cancellation fee"""
    if status in ["pending", "confirmed"]:
        return 0.0
    if status in ["preparing", "packing"]:
        return amount * 0.10
    return 0.0


async def log_action(refund_id: str, order_id: str, action: str, old_status: str, new_status: str, actor_type: str, error: str = None):
    """Log action"""
    try:
        await RefundLog.create(
            refund_id=refund_id,
            order_id=order_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            actor_type=actor_type,
            error=error
        )
    except:
        pass


# ============================================================
# CASHFREE
# ============================================================

async def cashfree_refund(order_id: str, amount: float, refund_id: str) -> tuple[bool, str]:
    """Create refund in Cashfree"""
    try:
        # TODO: Add your Cashfree credentials here
        CLIENT_ID = "your_cashfree_client_id"
        CLIENT_SECRET = "your_cashfree_client_secret"
        
        url = f"https://api.cashfree.com/pg/orders/{order_id}/refunds"
        headers = {
            "x-client-id": CLIENT_ID,
            "x-client-secret": CLIENT_SECRET,
            "Content-Type": "application/json"
        }
        payload = {
            "refund_amount": float(amount),
            "refund_note": "Customer cancellation"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                gw_id = data.get("refund", {}).get("refund_id")
                logger.info(f"[Cashfree] Refund: {refund_id} -> {gw_id}")
                return True, gw_id
            else:
                logger.error(f"[Cashfree] Error: {response.text}")
                return False, response.text
    except Exception as e:
        logger.error(f"[Cashfree] Exception: {e}")
        return False, str(e)


# ============================================================
# PHONEPE
# ============================================================

async def phonepe_refund(order_id: str, amount: float, refund_id: str) -> tuple[bool, str]:
    """Create refund in PhonePe"""
    try:
        # TODO: Add your PhonePe credentials here
        MERCHANT_ID = "your_phonepe_merchant_id"
        MERCHANT_SECRET = "your_phonepe_merchant_secret"
        
        url = "https://api.phonepe.com/apis/hermes/pg/v1/refunds"
        headers = {
            "X-MERCHANT-ID": MERCHANT_ID,
            "X-MERCHANT-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json"
        }
        payload = {
            "merchantTransactionId": order_id,
            "refundAmount": int(amount * 100),
            "refundNote": "Customer cancellation"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                gw_id = data.get("data", {}).get("refundId")
                logger.info(f"[PhonePe] Refund: {refund_id} -> {gw_id}")
                return True, gw_id
            else:
                logger.error(f"[PhonePe] Error: {response.text}")
                return False, response.text
    except Exception as e:
        logger.error(f"[PhonePe] Exception: {e}")
        return False, str(e)


# ============================================================
# API ENDPOINTS
# ============================================================

@router.get("/orders/{order_id}/cancel-check", response_model=CancelCheckResponse)
async def check_cancel(order_id: str):
    """Check if order can be cancelled"""
    order = await get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not can_cancel(order.status):
        return CancelCheckResponse(
            can_cancel=False,
            refund_amount=0,
            cancellation_fee=0,
            reason=f"Cannot cancel in {order.status} status",
            expected_by=""
        )
    
    amount = float(order.total)
    fee = get_fee(order.status, amount)
    
    return CancelCheckResponse(
        can_cancel=True,
        refund_amount=amount - fee,
        cancellation_fee=fee,
        reason="Cancellation allowed",
        expected_by=(datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
    )


@router.post("/orders/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(order_id: str, reason: str = "customer_request"):
    """Cancel order and create refund"""
    
    order = await get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not can_cancel(order.status):
        raise HTTPException(status_code=400, detail=f"Cannot cancel in {order.status} status")
    
    # Calculate refund
    amount = float(order.total)
    fee = get_fee(order.status, amount)
    refund_amount = amount - fee
    
    # Create refund
    refund_id = f"REF_{uuid.uuid4().hex[:12].upper()}"
    refund = await Refund.create(
        id=refund_id,
        order_id=order_id,
        user_id=order.user_id,
        refund_amount=Decimal(str(refund_amount)),
        cancellation_fee=Decimal(str(fee)),
        original_amount=Decimal(str(amount)),
        payment_method=order.payment_method,
        expected_completion=datetime.utcnow() + timedelta(days=3),
        reason=reason,
        status="initiated"
    )
    
    await log_action(refund_id, order_id, "initiated", None, "initiated", "customer")
    
    # Update order
    order.status = "cancelled"
    order.refund_id = refund_id
    await order.save()
    
    # Process refund
    gw_id = None
    status = "initiated"
    
    if order.payment_status == "paid":
        if order.payment_method == "cashfree":
            success, result = await cashfree_refund(order_id, refund_amount, refund_id)
            if success:
                gw_id = result
                status = "processing"
                await log_action(refund_id, order_id, "processing", "initiated", "processing", "system")
            else:
                await log_action(refund_id, order_id, "failed", "initiated", "failed", "system", error=result)
        
        elif order.payment_method == "phonepe":
            success, result = await phonepe_refund(order_id, refund_amount, refund_id)
            if success:
                gw_id = result
                status = "processing"
                await log_action(refund_id, order_id, "processing", "initiated", "processing", "system")
            else:
                await log_action(refund_id, order_id, "failed", "initiated", "failed", "system", error=result)
    
    # Update refund
    refund.status = status
    refund.gateway_refund_id = gw_id
    await refund.save()
    
    return CancelOrderResponse(
        success=True,
        refund_id=refund_id,
        status=status,
        refund_amount=refund_amount,
        cancellation_fee=fee
    )


@router.get("/refund/{refund_id}", response_model=RefundStatusResponse)
async def get_refund(refund_id: str):
    """Get refund status"""
    refund = await Refund.get_or_none(id=refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    return RefundStatusResponse(
        refund_id=refund.id,
        status=refund.status,
        refund_amount=float(refund.refund_amount),
        completed_at=refund.completed_at.strftime("%Y-%m-%d %H:%M:%S") if refund.completed_at else None
    )


@router.post("/webhook/cashfree")
async def cashfree_webhook(data: dict):
    """Cashfree webhook"""
    try:
        gw_id = data.get("refund_id")
        status = data.get("status")  # PROCESSED, FAILED
        
        refund = await Refund.get_or_none(gateway_refund_id=gw_id)
        if not refund:
            return {"ok": False}
        
        old_status = refund.status
        refund.status = "completed" if status == "PROCESSED" else "failed"
        if refund.status == "completed":
            refund.completed_at = datetime.utcnow()
        
        await refund.save()
        await log_action(refund.id, refund.order_id, "webhook", old_status, refund.status, "gateway")
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False}


@router.post("/webhook/phonepe")
async def phonepe_webhook(data: dict):
    """PhonePe webhook"""
    try:
        gw_id = data.get("refundId")
        status = data.get("status")  # PROCESSED, FAILED
        
        refund = await Refund.get_or_none(gateway_refund_id=gw_id)
        if not refund:
            return {"ok": False}
        
        old_status = refund.status
        refund.status = "completed" if status == "PROCESSED" else "failed"
        if refund.status == "completed":
            refund.completed_at = datetime.utcnow()
        
        await refund.save()
        await log_action(refund.id, refund.order_id, "webhook", old_status, refund.status, "gateway")
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False}
