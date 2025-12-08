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
            "return_url": f"{settings.FRONTEND_URL}/payment-status"
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


# ============================================================
# WEBHOOK FOR MULTI-ORDER PAYMENTS
# ============================================================

# @router.post("/webhook")
# async def cashfree_webhook(request: httpx.Request, redis = Depends(get_redis)):
#     """
#     Handle webhook for multi-order payments.
#     When payment succeeds, update ALL orders in the group.
#     """
    
#     try:
#         raw_body = await request.body()
#         body_str = raw_body.decode('utf-8')
        
#         print(f"[WEBHOOK] Received payment webhook")
        
#         if not body_str or body_str.strip() == "":
#             return {"status": "ignored", "message": "Empty webhook body"}
        
#         try:
#             payload = json.loads(body_str)
#         except json.JSONDecodeError as e:
#             raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
#         # Verify signature (if provided)
#         signature = request.headers.get("x-webhook-signature")
#         timestamp = request.headers.get("x-webhook-timestamp")
        
#         if signature and timestamp and CASHFREE_CLIENT_PAYMENT_SECRET:
#             signed_payload = f"{timestamp}.{body_str}"
#             computed_signature = hmac.new(
#                 CASHFREE_CLIENT_PAYMENT_SECRET.encode('utf-8'),
#                 signed_payload.encode('utf-8'),
#                 hashlib.sha256
#             ).hexdigest()
            
#             if not hmac.compare_digest(computed_signature, signature):
#                 print("[WEBHOOK] ❌ Invalid signature")
#                 raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
#         # Extract payment data
#         data = payload.get("data", {}) if "data" in payload else payload
#         link_id = data.get("link_id")
#         link_status = data.get("link_status")
        
#         print(f"[WEBHOOK] Payment ID: {link_id}, Status: {link_status}")
        
#         if not link_id:
#             raise HTTPException(status_code=400, detail="Missing link_id")
        
#         # Find ALL orders associated with this payment
#         orders = await Order.filter(cf_order_id=link_id).prefetch_related('user', 'items__item__vendor')
        
#         if not orders:
#             print(f"[WEBHOOK] No orders found for payment {link_id}")
#             return {"status": "ignored", "message": "No orders found"}
        
#         print(f"[WEBHOOK] Found {len(orders)} orders for payment {link_id}")
        
#         # Process payment status
#         if link_status == "PAID":
#             # Update ALL orders to PROCESSING
#             for order in orders:
#                 old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
                
#                 order.status = OrderStatus.PROCESSING
#                 order.payment_status = "paid"
                
#                 if order.metadata is None:
#                     order.metadata = {}
                
#                 if "cashfree" not in order.metadata:
#                     order.metadata["cashfree"] = {}
                
#                 order.metadata["cashfree"]["payment_status"] = "PAID"
#                 order.metadata["cashfree"]["paid_at"] = data.get("link_paid_at", datetime.utcnow().isoformat())
#                 order.metadata["cashfree"]["payment_amount"] = float(order.total)
                
#                 await order.save()
                
#                 print(f"[WEBHOOK] ✅ Order {order.id}: {old_status} → PROCESSING")
            
#             # Send notifications for all orders
#             try:
#                 # Notify customer once about all orders
#                 order_ids_str = ", ".join([o.id for o in orders])
#                 total_paid = sum(float(o.total) for o in orders)
                
#                 await send_notification(
#                     orders[0].user.id,
#                     "Payment Successful",
#                     f"Your payment of ₹{total_paid:.2f} for {len(orders)} orders was successful. Order IDs: {order_ids_str}"
#                 )
                
#                 # Notify each vendor
#                 vendor_notifications = {}
#                 for order in orders:
#                     if order.vendor_id:
#                         if order.vendor_id not in vendor_notifications:
#                             vendor_notifications[order.vendor_id] = []
#                         vendor_notifications[order.vendor_id].append(order.id)
                
#                 for vendor_id, order_ids in vendor_notifications.items():
#                     await send_notification(
#                         vendor_id,
#                         "New Paid Orders",
#                         f"Received {len(order_ids)} new paid orders: {', '.join(order_ids)}"
#                     )
                
#                 print(f"[WEBHOOK] ✅ Notifications sent")
                
#             except Exception as e:
#                 print(f"[WEBHOOK] Notification error: {e}")
            
#             return {
#                 "status": "success",
#                 "message": f"Payment processed for {len(orders)} orders",
#                 "orders_updated": [o.id for o in orders]
#             }
        
#         elif link_status == "FAILED":
#             for order in orders:
#                 order.payment_status = "failed"
#                 if order.metadata:
#                     order.metadata["cashfree"]["payment_status"] = "FAILED"
#                 await order.save()
            
#             print(f"[WEBHOOK] ❌ Payment failed for {len(orders)} orders")
            
#         elif link_status == "EXPIRED":
#             for order in orders:
#                 order.payment_status = "expired"
#                 if order.metadata:
#                     order.metadata["cashfree"]["payment_status"] = "EXPIRED"
#                 await order.save()
            
#             print(f"[WEBHOOK] ⏰ Payment expired for {len(orders)} orders")
        
#         return {"status": "success", "message": "Webhook processed"}
        
#     except Exception as e:
#         print(f"[WEBHOOK ERROR] {str(e)}")
#         import traceback
#         traceback.print_exc()
#         return {"status": "error", "message": str(e)}


# ============================================================
# VERIFY MULTI-ORDER PAYMENT
# ============================================================


# @router.get("/test/pay-last")
# @router.post("/test/pay-last")
# async def pay_last_order_no_auth():
#     """
#     TEST ONLY: Find and pay the most recent unpaid order.
#     Just open in browser: /payment/test/pay-last
    
#     ⚠️ REMOVE THIS ENDPOINT IN PRODUCTION!
#     """
    
#     # Find most recent unpaid order
#     order = await Order.filter(
#         payment_status="unpaid"
#     ).order_by('-created_at').first().prefetch_related('user', 'items__item__vendor')
    
#     if not order:
#         return {
#             "success": False,
#             "message": "No unpaid orders found in the system"
#         }
    
#     # Update order
#     old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    
#     order.status = OrderStatus.PROCESSING
#     order.payment_status = "paid"
    
#     if order.metadata is None:
#         order.metadata = {}
    
#     if "cashfree" not in order.metadata:
#         order.metadata["cashfree"] = {}
    
#     order.metadata["cashfree"]["payment_status"] = "PAID"
#     order.metadata["cashfree"]["paid_at"] = datetime.utcnow().isoformat()
#     order.metadata["cashfree"]["payment_amount"] = float(order.total)
#     order.metadata["cashfree"]["test_no_auth_last"] = True
    
#     await order.save()
    
#     print(f"[NO-AUTH LAST] ✅ Order {order.id}: {old_status} → PROCESSING")
    
#     # Send notifications
#     try:
#         await send_notification(
#             order.user.id,
#             "Payment Successful (TEST)",
#             f"Order #{order.id} payment confirmed."
#         )
#     except Exception as e:
#         print(f"[NO-AUTH LAST] Notification error: {e}")
    
#     return {
#         "success": True,
#         "message": "✅ Most recent order marked as paid!",
#         "order_id": order.id,
#         "customer_name": order.user.name,
#         "old_status": old_status,
#         "new_status": "processing",
#         "payment_status": "paid",
#         "total": float(order.total),
#         "order_date": order.order_date.isoformat(),
#         "note": "⚠️ This is a TEST payment - remove this endpoint in production!"
#     }


#     return {
#         "success": True,
#         "message": "Last order marked as paid",
#         "order_id": order.id,
#         "old_status": old_status,
#         "new_status": "processing",
#         "total": float(order.total)
#     }


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