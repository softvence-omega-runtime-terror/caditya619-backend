# app/main.py
from fastapi import FastAPI, APIRouter, HTTPException, Request
from pydantic import BaseModel, validator
import httpx
import uuid
import re
from app.config import settings
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from app.config import settings
from applications.customer.models import Order

CASHFREE_CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"

class PaymentInitiateRequest(BaseModel):
    order_id: str

class PaymentLinkResponse(BaseModel):
    success: bool
    order_id: str
    cf_order_id: str
    payment_link: str
    message: str

router = APIRouter(prefix='/payment', tags=['Payment'])

@router.post("/initiate", response_model=PaymentLinkResponse)
async def create_payment_link(req: PaymentInitiateRequest):
    """Create a Cashfree payment link for an order"""
    
    # Fetch order from database
    order = await Order.get_or_none(id=req.order_id).prefetch_related(
        'user', 
        'shipping_address'
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if payment method is cashfree
    payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
    if payment_method.lower() != "cashfree":
        raise HTTPException(
            status_code=400, 
            detail=f"Order payment method is {payment_method}, not Cashfree"
        )
    
    # Check if order is in pending status
    order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    if order_status.lower() != "placed":
        raise HTTPException(
            status_code=400, 
            detail=f"Order is already {order_status}. Cannot create payment link."
        )
    
    # Get customer details from order
    customer_name = order.shipping_address.full_name or order.user.name or "Customer"
    customer_email = order.shipping_address.email or order.user.email or f"customer_{order.user.id}@example.com"
    customer_phone = order.shipping_address.phone_number or "9999999999"
    
    # Prepare Cashfree API headers
    headers = {
        "x-client-id": CASHFREE_CLIENT_ID,
        "x-client-secret": CASHFREE_CLIENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json"
    }
    
    # Generate unique Cashfree order ID
    cf_order_id = f"CF_{req.order_id}_{uuid.uuid4().hex[:8].upper()}"
    
    # Prepare payment link payload
    payload = {
        "link_id": cf_order_id,
        "link_amount": float(order.total),
        "link_currency": "INR",
        "link_purpose": f"Payment for order {req.order_id}",
        "customer_details": {
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "customer_name": customer_name
        },
        "link_notify": {
            "send_sms": True,
            "send_email": True
        },
        "link_meta": {
            "order_id": req.order_id,
            "user_id": str(order.user.id)
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{CASHFREE_BASE}/links",
                json=payload,
                headers=headers
            )
        
        data = resp.json()
        
        if resp.status_code not in [200, 201]:
            error_msg = data.get("message", "Payment link creation failed")
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Cashfree API error: {error_msg}"
            )
        
        # Extract payment link
        payment_link = data.get("link_url")
        
        if not payment_link:
            raise HTTPException(
                status_code=500,
                detail="Payment link not received from Cashfree"
            )
        
        # Update order metadata with Cashfree details
        if order.metadata is None:
            order.metadata = {}
        
        order.metadata["cashfree"] = {
            "cf_link_id": cf_order_id,
            "payment_link": payment_link,
            "link_status": data.get("link_status"),
            "created_at": data.get("link_created_at")
        }
        
        await order.save(update_fields=["metadata"])
        
        return PaymentLinkResponse(
            success=True,
            order_id=req.order_id,
            cf_order_id=cf_order_id,
            payment_link=payment_link,
            message="Payment link created successfully"
        )
        
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to Cashfree: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment link: {str(e)}"
        )


@router.post("/webhook")
async def cashfree_webhook(request: dict):
    """Handle Cashfree payment webhook notifications"""
    
    # Extract relevant data from webhook
    link_id = request.get("link_id")
    link_status = request.get("link_status")
    
    if not link_id:
        raise HTTPException(status_code=400, detail="Invalid webhook data")
    
    # Extract order_id from link_id (format: CF_order_xxx_HASH)
    try:
        order_id = "_".join(link_id.split("_")[1:-1])
    except:
        raise HTTPException(status_code=400, detail="Invalid link_id format")
    
    # Find and update order
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Update order based on payment status
    if link_status == "PAID":
        order.status = "CONFIRMED"  # or whatever status enum you use
        if order.metadata:
            order.metadata["cashfree"]["payment_status"] = "PAID"
            order.metadata["cashfree"]["paid_at"] = request.get("link_paid_at")
        await order.save()
        
        # TODO: Send notifications to customer and vendor
        
    elif link_status == "EXPIRED":
        if order.metadata:
            order.metadata["cashfree"]["payment_status"] = "EXPIRED"
        await order.save()
    
    return {"status": "success"}

# @router.post("/webhook/cashfree/")
# async def cashfree_webhook(request: Request):
#     payload = await request.json()
#     order_id = payload.get("order_id")
#     status = payload.get("order_status")

#     if order_id in ORDERS_DB:
#         ORDERS_DB[order_id]["status"] = status

#     return {"status": "ok", "received_order_id": order_id, "status_from_cashfree": status}

# # Include router
# app.include_router(router)

# # Test root endpoint
# @app.get("/")
# def read_root():
#     return {"message": "FastAPI + Cashfree Sandbox Example"}
