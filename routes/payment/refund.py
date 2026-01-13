# ============================================================
# REFUND SYSTEM - SIMPLE VERSION
# One file: refund.py
# ============================================================

import logging
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from tortoise import fields
from tortoise.models import Model
from pydantic import BaseModel
from typing import Optional
import httpx
from app.config import settings
from applications.payment.models import Refund, RefundLog, CancellationReason, ReportAndIssue
from applications.customer.models import Order
from applications.user.models import User
from app.token import get_current_user
from app.utils.file_manager import save_file, delete_file, update_file
from tortoise.contrib.pydantic import pydantic_model_creator
from routes.payment.payment import CASHFREE_ENV

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/refunds", tags=["refunds"])

# ============================================================
# DATABASE MODELS
# ============================================================

# class Refund(Model):
#     """Refund tracking"""
#     id = fields.CharField(max_length=255, pk=True)
#     order_id = fields.CharField(max_length=255, index=True)
#     user_id = fields.IntField(index=True)
    
#     refund_amount = fields.DecimalField(max_digits=10, decimal_places=2)
#     cancellation_fee = fields.DecimalField(max_digits=10, decimal_places=2, default=0)
#     original_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    
#     status = fields.CharField(max_length=50, default="initiated", index=True)
#     reason = fields.CharField(max_length=100, default="customer_cancellation")
    
#     payment_method = fields.CharField(max_length=50, null=True)
#     gateway_refund_id = fields.CharField(max_length=255, null=True, unique=True)
    
#     expected_completion = fields.DatetimeField(null=True)
#     completed_at = fields.DatetimeField(null=True)
#     created_at = fields.DatetimeField(auto_now_add=True, index=True)

#     class Meta:
#         table = "refunds"


# class RefundLog(Model):
#     """Audit trail"""
#     refund_id = fields.CharField(max_length=255, index=True)
#     order_id = fields.CharField(max_length=255)
#     action = fields.CharField(max_length=100)
#     old_status = fields.CharField(max_length=50, null=True)
#     new_status = fields.CharField(max_length=50, null=True)
#     actor_type = fields.CharField(max_length=50)  # customer, gateway, system
#     error = fields.TextField(null=True)
#     created_at = fields.DatetimeField(auto_now_add=True, index=True)

#     class Meta:
#         table = "refund_logs"


# ============================================================
# SCHEMAS
# ============================================================


ReportAndIssue_Pydantic = pydantic_model_creator(ReportAndIssue, name="ReportAndIssue")

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
    gw_id: Optional[str] = None


class RefundStatusResponse(BaseModel):
    refund_id: str
    status: str
    refund_amount: float
    completed_at: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================

async def get_order(order_id: str):
    """Get order - replace with your actual import"""
    from applications.customer.models import Order
    return await Order.get_or_none(parent_order_id=order_id)


def can_cancel(status: str) -> bool:
    """Check if order status allows cancellation"""
    blocked = ["shipped", "out_for_delivery", "delivered", "cancelled"]
    return status.lower() not in blocked


def get_fee(status: str, amount: float) -> float:
    """Calculate cancellation fee"""
    if status in ["processing"]:
        return 0.0
    if status in ["preparing", "confirmed"]:
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
    print(f"Initiating Cashfree refund for order {order_id} amount {amount}")
    try:
        # TODO: Add your Cashfree credentials here
        CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
        CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
        CASHFREE_API_VERSION = "2023-08-01"
        CASHFREE_ENV = settings.CASHFREE_ENV
        CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"

        url = f"{CASHFREE_BASE}/orders/{order_id}/refunds"
        headers = {
            "x-client-id": CLIENT_ID,
            "x-client-secret": CLIENT_SECRET,
            "x-api-version": CASHFREE_API_VERSION,
            "Content-Type": "application/json"
        }
        payload = {
            "refund_amount": float(amount),
            "refund_id": refund_id,
            "refund_note": "Customer cancellation",
            "refund_speed": "STANDARD"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                print(f"[Cashfree] Refund response: {data}")
                gw_id = data.get("refund", {}).get("refund_id")
                logger.info(f"[Cashfree] Refund: {refund_id} -> {gw_id}")
                return True, gw_id
            else:
                logger.error(f"[Cashfree] Error: {response.text}")
                return False, response.text
    except Exception as e:
        logger.error(f"[Cashfree] Exception: {e}")
        return False, str(e)
    


async def cashfree_refund_status_check(order_id: str, refund_id: str) -> tuple[bool, str]:
    """Create refund in Cashfree"""
    try:
        # TODO: Add your Cashfree credentials here
        CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
        CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
        CASHFREE_API_VERSION = "2023-08-01"
        CASHFREE_ENV = settings.CASHFREE_ENV
        CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"

        url = f"{CASHFREE_BASE}/orders/{order_id}/refunds/{refund_id}"

        headers = {
            "x-client-id": CLIENT_ID,
            "x-client-secret": CLIENT_SECRET,
            "x-api-version": CASHFREE_API_VERSION,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            print(f"[Cashfree] Refund status: {data}")
            logger.info(f"[Cashfree] Refund status {refund_id}: {data}")
            return True, data
        else:
            logger.error(
                f"[Cashfree] Refund status error {response.status_code}: {response.text}"
            )
            return False, response.text

    except Exception as e:
        logger.error(f"[Cashfree] Exception in refund status check: {e}")
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
    
    orders = await Order.filter(parent_order_id=order_id)
    if not orders:
        raise HTTPException(status_code=404, detail="Order not found")
    
    #order = orders[0]  # Assuming parent_order_id is same for all combined orders
    total = 0.0
    status = ""

    for order in orders:
    
        if not can_cancel(order.status):
            raise HTTPException(status_code=400, detail=f"Cannot cancel in {order.status} status")
        
        method = order.payment_method.lower()
        total += float(order.total)
        status = order.status
        if order.payment_method == "cod":
            order.status = "cancelled"
            await order.save()
    if method == "cod":
        return CancelOrderResponse(
            success=True,
            refund_id="",
            status="cancelled",
            refund_amount=0.0,
            cancellation_fee=0.0
        )
    
    # Calculate refund
    amount = float(total)
    fee = get_fee(status, amount)
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
    # order.status = "cancelled"
    # order.refund_id = refund_id
    # await order.save()
    
    # Process refund
    gw_id = None
    status = "initiated"
    
    if order.payment_status == "paid":
        if order.payment_method == "cashfree":
            success, result = await cashfree_refund(order_id, refund_amount, refund_id)
            if success:
                gw_id = result
                print(gw_id)
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


    if status == "processing":
        for order in orders:
            order.status = "cancelled"
            order.refund_id = refund_id
            await order.save()
    
    # Update refund
    refund.status = status
    refund.gateway_refund_id = gw_id
    await refund.save()
    
    return CancelOrderResponse(
        success=True,
        refund_id=refund_id,
        status=status,
        refund_amount=refund_amount,
        cancellation_fee=fee,
        gw_id=gw_id
    )


@router.get("/refund/{order_id}", response_model=RefundStatusResponse)
async def get_refund(order_id: str):
    """Get refund status"""
    # refund = await Refund.get_or_none(id=refund_id)
    refund = await Refund.get_or_none(order_id=order_id)
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
        order_id = data.get("order_id")
        
        #refund = await Refund.get_or_none(gateway_refund_id=gw_id)
        refund = await Refund.get_or_none(order_id=order_id)
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



@router.post("/refund/{order_id}/check-status")
async def check_refund_status(order_id: str):
    refund = await Refund.get_or_none(order_id=order_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    if refund.payment_method == "cashfree":
        status, data = await cashfree_refund_status_check(order_id, refund.id)
    else:
        data = {"error": "Unsupported gateway"}
        return data
    
    return {"status": status, "data": data}



# ============================================================
#  REPORTS AND ISSUES
# ============================================================

@router.post("/cancellation-reasons")
async def add_cancellation_reason(reason: str = Form(...), order_id: Optional[str] = Form(None), user: User = Depends(get_current_user)):
    """Add a predefined cancellation reason"""
    existing = await CancellationReason.get_or_none(reason=reason)
    if existing:
        raise HTTPException(status_code=400, detail="Reason already exists")
    
    cr = await CancellationReason.create(
        reason=reason,
        order_id=order_id
    )
    return {"id": cr.id, "reason": cr.reason}



@router.post("/reports-and-issues")
async def log_report_issue(order_id: str = Form(...), 
                           reason: str = Form(...), 
                           details: Optional[str] = Form(None), 
                           file: Optional[UploadFile] = File(None),
                           transection_id: Optional[str] = Form(None), 
                           user: User = Depends(get_current_user)
                        ):

    if file and file.filename:
        file_path = await save_file(
            file, upload_to="reports_and_issues/"
        )
    else:
        file_path = None

    report = await ReportAndIssue.create(
        order_id=order_id,
        reason=reason,
        details=details,
        image=file_path,
        transection_id=transection_id
    )

    return await ReportAndIssue_Pydantic.from_tortoise_orm(report)




