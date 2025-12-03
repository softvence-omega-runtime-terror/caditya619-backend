from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from applications.customer.schemas import PaymentInitiateSchema, PaymentCallbackSchema, PaymentLinkResponse, PaymentResponseSchema
from applications.customer.models import Order, OrderStatus
from applications.user.models import User
from app.config import settings
from app.token import get_current_user
import httpx
import uuid
import re
import time

router = APIRouter(prefix='/order_payment', tags=['order_payment'])

CASHFREE_CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2022-09-01"

class PaymentInitiateRequest(BaseModel):
    order_id: str

class PaymentLinkResponse(BaseModel):
    success: bool
    order_id: str
    cf_order_id: str
    payment_link: str
    message: str



@router.post("/initiate", response_model=PaymentLinkResponse)
async def initiate_payment(
    request: PaymentInitiateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate payment link for an order
    """
    try:
        # 1. Get the order
        order = await Order.get_or_none(
            id=request.order_id, 
            user_id=current_user.id
        ).prefetch_related("shipping_address")
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # 2. Validate order status
        current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        if current_status.lower() != "placed":
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot process payment. Order status is '{current_status}'"
            )
        
        # 3. Validate payment method
        payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
        if payment_method.lower() != "cashfree":
            raise HTTPException(
                status_code=400,
                detail="This order does not use Cashfree payment method"
            )
        
        # 4. Generate unique Cashfree order ID
        cf_order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        
        # 5. Prepare customer details
        customer_phone = order.shipping_address.phone_number if order.shipping_address else current_user.phone_number
        customer_email = current_user.email or f"customer_{current_user.id}@example.com"
        customer_name = order.shipping_address.full_name if order.shipping_address else current_user.name
        
        # Validate and format phone number
        if customer_phone:
            customer_phone = re.sub(r"[^\d+]", "", customer_phone)
            if not re.match(r"^(\+?\d{10,15})$", customer_phone):
                customer_phone = "+919999999999"  # Fallback
        else:
            customer_phone = "+919999999999"
        
        # 6. Prepare Cashfree API headers
        headers = {
            "x-client-id": CASHFREE_CLIENT_ID,
            "x-client-secret": CASHFREE_CLIENT_SECRET,
            "x-api-version": CASHFREE_API_VERSION,
            "Content-Type": "application/json"
        }
        
        # 7. Prepare order payload for Cashfree
        payload = {
            "order_id": cf_order_id,
            "order_amount": float(order.total),
            "order_currency": "INR",
            "customer_details": {
                "customer_id": str(current_user.id),
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone
            },
            "order_meta": {
                "return_url": f"{settings.FRONTEND_URL}/payment/callback?order_id={order.id}",
                "notify_url": f"{settings.BACKEND_URL}/payment/webhook/cashfree"
            }
        }
        
        print(f"Sending to Cashfree: {payload}")
        
        # 8. Call Cashfree API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CASHFREE_BASE}/orders",
                json=payload,
                headers=headers,
                timeout=30.0
            )
        
        response_data = response.json()
        print(f"Cashfree Response: {response_data}")
        
        # 9. Handle API errors
        if response.status_code != 200:
            error_message = response_data.get("message", "Unknown error")
            raise HTTPException(
                status_code=400,
                detail=f"Cashfree API error: {error_message}"
            )
        
        # 10. Extract payment link
        payment_link = response_data.get("payment_link")
        
        if not payment_link:
            raise HTTPException(
                status_code=500,
                detail="Payment link not received from Cashfree"
            )
        
        # 11. Save Cashfree details to order
        if order.metadata:
            order.metadata["cf_order_id"] = cf_order_id
            order.metadata["payment_link"] = payment_link
        else:
            order.metadata = {
                "cf_order_id": cf_order_id,
                "payment_link": payment_link
            }
        
        await order.save()
        
        # 12. Return payment link
        return PaymentLinkResponse(
            success=True,
            order_id=order.id,
            cf_order_id=cf_order_id,
            payment_link=payment_link,
            message="Redirect user to payment_link to complete payment"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error initiating payment: {str(e)}"
        )








@router.post("/webhook/cashfree")
async def cashfree_webhook(request: Request):
    """
    Webhook to receive payment status from Cashfree
    """
    try:
        payload = await request.json()
        
        cf_order_id = payload.get("order_id")
        payment_status = payload.get("order_status")  # SUCCESS, FAILED, PENDING
        
        if not cf_order_id:
            return {"status": "error", "message": "Missing order_id"}
        
        # Extract original order ID from Cashfree order ID (CF_order_xxx_HASH)
        parts = cf_order_id.split("_")
        if len(parts) >= 3:
            order_id = "_".join(parts[1:-1])  # Reconstruct order_xxx
        else:
            return {"status": "error", "message": "Invalid order_id format"}
        
        # Find and update order
        order = await Order.get_or_none(id=order_id)
        
        if not order:
            return {"status": "error", "message": "Order not found"}
        
        # Update order based on payment status
        if payment_status == "PAID":
            order.status = OrderStatus.CONFIRMED
            order.transaction_id = payload.get("cf_payment_id")
        elif payment_status == "FAILED":
            order.status = OrderStatus.CANCELLED
        
        # Update metadata
        if order.metadata:
            order.metadata["payment_status"] = payment_status
            order.metadata["payment_time"] = payload.get("payment_time")
        else:
            order.metadata = {
                "payment_status": payment_status,
                "payment_time": payload.get("payment_time")
            }
        
        await order.save()
        
        return {
            "status": "ok",
            "order_id": order_id,
            "cf_order_id": cf_order_id,
            "payment_status": payment_status
        }
        
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/callback")
async def payment_callback(
    callback_data: PaymentCallbackSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Handle payment callback from frontend after payment completion
    """
    try:
        order = await Order.get_or_none(
            id=callback_data.order_id,
            user_id=current_user.id
        )
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Verify payment status with Cashfree
        headers = {
            "x-client-id": CASHFREE_CLIENT_ID,
            "x-client-secret": CASHFREE_CLIENT_SECRET,
            "x-api-version": CASHFREE_API_VERSION,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{CASHFREE_BASE}/orders/{callback_data.cf_order_id}",
                headers=headers,
                timeout=30.0
            )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Failed to verify payment status"
            )
        
        payment_data = response.json()
        verified_status = payment_data.get("order_status")
        
        # Update order status based on verified payment
        if verified_status == "PAID":
            order.status = OrderStatus.CONFIRMED
            order.transaction_id = callback_data.transaction_id or payment_data.get("cf_payment_id")
        elif verified_status == "FAILED":
            order.status = OrderStatus.CANCELLED
        
        await order.save()
        
        return {
            "success": True,
            "order_id": order.id,
            "payment_status": verified_status,
            "order_status": order.status.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing callback: {str(e)}"
        )


@router.get("/status/{order_id}")
async def get_payment_status(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Check payment status for an order
    """
    try:
        order = await Order.get_or_none(
            id=order_id,
            user_id=current_user.id
        )
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        payment_status = "pending"
        if order.metadata and "payment_status" in order.metadata:
            payment_status = order.metadata["payment_status"]
        
        return {
            "order_id": order.id,
            "order_status": order.status.value,
            "payment_status": payment_status,
            "transaction_id": order.transaction_id,
            "total": float(order.total)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving payment status: {str(e)}"
        )