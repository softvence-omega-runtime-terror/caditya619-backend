# ============================================================
# MULTI-ORDER PAYMENT LINK - routes/payment/routes.py
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from typing import List, Optional
import httpx
import uuid
from datetime import datetime
from decimal import Decimal

from app.redis import get_redis
from applications.customer.models import Order, OrderStatus
from app.config import settings
from routes.rider.notifications import send_notification

CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"

# ============================================================
# SCHEMAS
# ============================================================

class PaymentInitiateRequest(BaseModel):
    order_ids: List[str]  # Array of order IDs
    
    @validator('order_ids')
    def validate_order_ids(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one order_id is required")
        if len(v) > 10:  # Limit to prevent abuse
            raise ValueError("Maximum 10 orders can be paid together")
        return v

class OrderSummary(BaseModel):
    order_id: str
    total: float
    vendor_name: str
    items_count: int

class PaymentLinkResponse(BaseModel):
    success: bool
    orders: List[OrderSummary]
    cf_payment_id: str
    payment_link: str
    message: str
    total_amount: float
    orders_count: int

router = APIRouter(prefix='/payment', tags=['Payment'])

# ============================================================
# CREATE PAYMENT LINK FOR MULTIPLE ORDERS
# ============================================================

@router.post("/initiate", response_model=PaymentLinkResponse)
async def create_payment_link(req: PaymentInitiateRequest):
    """
    Create a single payment link for multiple orders.
    All orders must belong to the same customer and use Cashfree payment method.
    """
    
    # Step 1: Fetch all orders
    orders = await Order.filter(id__in=req.order_ids).prefetch_related(
        'user',
        'items',
        'vendor'
    )
    
    if len(orders) != len(req.order_ids):
        raise HTTPException(
            status_code=404,
            detail="Some orders not found"
        )
    
    # Step 2: Validate all orders
    customer_id = None
    customer_name = None
    customer_email = None
    customer_phone = None
    total_amount = Decimal("0")
    order_summaries = []
    
    for order in orders:
        # Check customer consistency
        if customer_id is None:
            customer_id = order.user_id
            customer_name = order.user.name or "Customer"
            customer_email = order.user.email or f"customer_{order.user.id}@example.com"
            customer_phone = order.user.phone or "9999999999"
        elif order.user_id != customer_id:
            raise HTTPException(
                status_code=400,
                detail="All orders must belong to the same customer"
            )
        
        # Check payment method
        payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
        if payment_method.lower() != "cashfree":
            raise HTTPException(
                status_code=400,
                detail=f"Order {order.id} payment method is {payment_method}, not Cashfree"
            )
        
        # Check order status
        order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        if order_status.lower() != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Order {order.id} is already {order_status}. Cannot create payment link."
            )
        
        # Check payment status
        if order.payment_status != "unpaid":
            raise HTTPException(
                status_code=400,
                detail=f"Order {order.id} is already paid or payment in progress"
            )
        
        # Get vendor name
        vendor_name = "Unknown Vendor"
        if order.vendor:
            vendor_name = order.vendor.name
        elif order.metadata and "vendor_info" in order.metadata:
            vendor_name = order.metadata["vendor_info"].get("vendor_name", "Unknown Vendor")
        
        # Calculate total
        total_amount += order.total
        
        # Build order summary
        order_summaries.append(OrderSummary(
            order_id=order.id,
            total=float(order.total),
            vendor_name=vendor_name,
            items_count=len(order.items)
        ))
    
    # Step 3: Create combined payment link
    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID.strip(),
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET.strip(),
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json"
    }
    
    # Generate unique payment ID for multiple orders
    cf_payment_id = f"PAY_{uuid.uuid4().hex[:12].upper()}"
    
    # Build payment purpose description
    order_list = ", ".join([o.id for o in orders])
    payment_purpose = f"Payment for {len(orders)} orders: {order_list[:100]}"  # Truncate if too long
    
    payload = {
        "link_id": cf_payment_id,
        "link_amount": float(total_amount),
        "link_currency": "INR",
        "link_purpose": payment_purpose,
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
            "order_ids": req.order_ids,  # Store all order IDs
            "user_id": str(customer_id),
            "orders_count": len(orders),
            "return_url": f"{settings.BACKEND_URL}/payment/payment/test/pay-last"
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"[PAYMENT] Creating link for {len(orders)} orders, total: ₹{total_amount}")
            
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
        
        payment_link = data.get("link_url")
        
        if not payment_link:
            raise HTTPException(
                status_code=500,
                detail="Payment link not received from Cashfree"
            )
        
        # Step 4: Update all orders with payment link info
        payment_info = {
            "cf_payment_id": cf_payment_id,
            "payment_link": payment_link,
            "link_status": data.get("link_status"),
            "created_at": data.get("link_created_at"),
            "is_combined_payment": True,
            "combined_order_ids": req.order_ids,
            "combined_total": float(total_amount)
        }
        
        for order in orders:
            if order.metadata is None:
                order.metadata = {}
            
            order.metadata["cashfree"] = payment_info.copy()
            order.cf_order_id = cf_payment_id  # Store for easy lookup
            
            await order.save(update_fields=["metadata", "cf_order_id"])
        
        print(f"[PAYMENT] ✅ Payment link created: {payment_link}")
        
        return PaymentLinkResponse(
            success=True,
            orders=order_summaries,
            cf_payment_id=cf_payment_id,
            payment_link=payment_link,
            message=f"Payment link created for {len(orders)} orders",
            total_amount=float(total_amount),
            orders_count=len(orders)
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




@router.get("/test/pay-last")
@router.post("/test/pay-last")
async def pay_last_order_no_auth():
    """Test endpoint to mark the most recent unpaid order(s) as paid"""
    
    order = await Order.filter(
        payment_status="unpaid"
    ).order_by('-created_at').first().prefetch_related('user', 'items__item__vendor')
    
    if not order:
        return {
            "success": False,
            "message": "No unpaid orders found in the system"
        }
    
    # Check if this order is part of a combined payment
    orders_to_process = [order]
    is_combined = False
    cf_payment_id = None
    
    if order.metadata and "cashfree" in order.metadata:
        cashfree_data = order.metadata["cashfree"]
        
        # Check if this is a combined payment
        if cashfree_data.get("is_combined_payment") and cashfree_data.get("combined_order_ids"):
            is_combined = True
            cf_payment_id = cashfree_data.get("cf_payment_id")
            combined_order_ids = cashfree_data["combined_order_ids"]
            
            # Fetch all orders in the combined payment
            orders_to_process = await Order.filter(
                id__in=combined_order_ids
            ).prefetch_related('user', 'items__item__vendor')
            
            print(f"[NO-AUTH LAST] Found combined payment with {len(orders_to_process)} orders")
    
    # Process all orders
    processed_orders = []
    total_amount = Decimal("0")
    
    for ord in orders_to_process:
        old_status = ord.status.value if hasattr(ord.status, 'value') else str(ord.status)
        
        ord.status = OrderStatus.PROCESSING
        ord.payment_status = "paid"
        
        if ord.metadata is None:
            ord.metadata = {}
        
        if "cashfree" not in ord.metadata:
            ord.metadata["cashfree"] = {}
        
        # Update payment metadata
        ord.metadata["cashfree"]["payment_status"] = "PAID"
        ord.metadata["cashfree"]["paid_at"] = datetime.utcnow().isoformat()
        ord.metadata["cashfree"]["payment_amount"] = float(ord.total)
        ord.metadata["cashfree"]["test_no_auth_last"] = True
        
        # Preserve combined payment info if exists
        if is_combined and cf_payment_id:
            ord.metadata["cashfree"]["is_combined_payment"] = True
            ord.metadata["cashfree"]["cf_payment_id"] = cf_payment_id
        
        await ord.save()
        
        total_amount += ord.total
        
        print(f"[NO-AUTH LAST] ✅ Order {ord.id}: {old_status} → PROCESSING")
        
        # Send notification to customer — message depends on payment method
        try:
            pm = ord.payment_method.value if hasattr(ord.payment_method, 'value') else str(ord.payment_method)
            pm = (pm or "").lower()
            if pm == "cashfree":
                title = "Payment Successful"
                body = "Your payment is successful."
            else:
                title = "Order Processing"
                body = "Your order is now processing."

            await send_notification(
                ord.user.id,
                title,
                body
            )
        except Exception as e:
            print(f"[NO-AUTH LAST] Notification error for order {ord.id}: {e}")
        
        processed_orders.append({
            "order_id": ord.id,
            "old_status": old_status,
            "total": float(ord.total)
        })
    
    # Prepare response
    response = {
        "success": True,
        "message": f"✅ {'Combined payment' if is_combined else 'Order'} marked as paid!",
        "orders_count": len(processed_orders),
        "total_amount": float(total_amount),
        "processed_orders": processed_orders,
        "customer_name": order.user.name,
        "payment_status": "paid",
        "is_combined_payment": is_combined,
        "note": "⚠️ This is a TEST payment - remove this endpoint in production!"
    }
    
    if is_combined and cf_payment_id:
        response["cf_payment_id"] = cf_payment_id
    
    return response


@router.get("/verify/{cf_payment_id}")
async def verify_multi_order_payment(cf_payment_id: str):
    """
    Verify payment status for multiple orders.
    """
    
    # Find all orders with this payment ID
    orders = await Order.filter(cf_order_id=cf_payment_id).prefetch_related('user', 'items')
    
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found for this payment")
    
    # Call Cashfree API to check status
    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{CASHFREE_BASE}/links/{cf_payment_id}",
                headers=headers
            )
            
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Failed to verify payment: {resp.text}"
                )
            
            data = resp.json()
            link_status = data.get("link_status")
            
            print(f"[VERIFY] Payment {cf_payment_id} status: {link_status}")
            
            # Update orders if paid but not yet updated
            if link_status == "PAID":
                for order in orders:
                    if order.payment_status != "paid":
                        order.status = OrderStatus.PROCESSING
                        order.payment_status = "paid"
                        
                        if order.metadata:
                            order.metadata["cashfree"]["payment_status"] = "PAID"
                            order.metadata["cashfree"]["paid_at"] = data.get("link_paid_at")
                        
                        await order.save()
                        print(f"[VERIFY] ✅ Updated order {order.id}")
            
            return {
                "cf_payment_id": cf_payment_id,
                "link_status": link_status,
                "orders_count": len(orders),
                "orders": [
                    {
                        "order_id": o.id,
                        "payment_status": o.payment_status,
                        "order_status": o.status.value if hasattr(o.status, 'value') else str(o.status),
                        "total": float(o.total)
                    }
                    for o in orders
                ],
                "total_amount": sum(float(o.total) for o in orders),
                "paid_at": data.get("link_paid_at")
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying payment: {str(e)}")