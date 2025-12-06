from datetime import datetime
from fastapi import Depends, FastAPI, APIRouter, HTTPException, Request
from pydantic import BaseModel, validator
import httpx
import uuid
import json
import hmac
import hashlib
from app.config import settings
from app.redis import get_redis
from app.token import get_current_user
from applications.customer.models import Order, OrderStatus
from applications.user.models import User
from applications.user.vendor import VendorProfile
from routes.rider.websocket_endpoints import send_notification
from app.utils.websocket_manager import manager


CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
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

# @router.post("/initiate", response_model=PaymentLinkResponse)
# async def create_payment_link(req: PaymentInitiateRequest):
    
#     order = await Order.get_or_none(id=req.order_id).prefetch_related(
#         'user', 
#         'shipping_address'
#     )


    
#     if not order:
#         raise HTTPException(status_code=404, detail="Order not found")
    
#     payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
    
#     if payment_method.lower() != "cashfree":
#         raise HTTPException(
#             status_code=400, 
#             detail=f"Order payment method is {payment_method}, not Cashfree"
#         )
    
#     order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
#     if order_status.lower() != "pending":
#         raise HTTPException(
#             status_code=400, 
#             detail=f"Order is already {order_status}. Cannot create payment link."
#         )
    
#     customer_name = order.shipping_address.full_name or order.user.name or "Customer"
#     customer_email = order.shipping_address.email or order.user.email or f"customer_{order.user.id}@example.com"
#     customer_phone = order.shipping_address.phone_number or "9999999999"
    
#     headers = {
#         "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
#         "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET,
#         "x-api-version": CASHFREE_API_VERSION,
#         "Content-Type": "application/json"
#     }
    
#     cf_order_id = f"CF_{req.order_id}_{uuid.uuid4().hex[:8].upper()}"
    
#     # FIXED: Added return_url in link_meta for callback
#     payload = {
#         "link_id": cf_order_id,
#         "link_amount": float(order.total),
#         "link_currency": "INR",
#         "link_purpose": f"Payment for order {req.order_id}",
#         "customer_details": {
#             "customer_phone": customer_phone,
#             "customer_email": customer_email,
#             "customer_name": customer_name
#         },
#         "link_notify": {
#             "send_sms": True,
#             "send_email": True
#         },
#         "link_meta": {
#             "order_id": req.order_id,
#             "user_id": str(order.user.id),
#             "return_url": f"{settings.BACKEND_URL}/payment/payment/webhook/test"
#         }
#     }

#     # http://localhost:5173/payment-status?order_id=76
#     # http://127.0.0.1:8000/
#     # "return_url": f"{settings.FRONTEND_URL}/payment-status?order_id={req.order_id}"

    
#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             resp = await client.post(
#                 f"{CASHFREE_BASE}/links",
#                 json=payload,
#                 headers=headers
#             )
        
#         data = resp.json()
        
#         if resp.status_code not in [200, 201]:
#             error_msg = data.get("message", "Payment link creation failed")
#             raise HTTPException(
#                 status_code=resp.status_code,
#                 detail=f"Cashfree API error: {error_msg}"
#             )
        
#         payment_link = data.get("link_url")
        
#         if not payment_link:
#             raise HTTPException(
#                 status_code=500,
#                 detail="Payment link not received from Cashfree"
#             )
        
#         if order.metadata is None:
#             order.metadata = {}
        
#         order.metadata["cashfree"] = {
#             "cf_link_id": cf_order_id,
#             "payment_link": payment_link,
#             "link_status": data.get("link_status"),
#             "created_at": data.get("link_created_at")
#         }
        
#         await order.save(update_fields=["metadata"])
        
#         return PaymentLinkResponse(
#             success=True,
#             order_id=req.order_id,
#             cf_order_id=cf_order_id,
#             payment_link=payment_link,
#             message="Payment link created successfully"
#         )
        
#     except httpx.RequestError as e:
#         raise HTTPException(
#             status_code=503,
#             detail=f"Failed to connect to Cashfree: {str(e)}"
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error creating payment link: {str(e)}"
#         )


@router.get("/webhook")
async def cashfree_webhook(request: Request, redis = Depends(get_redis)):
    """
    Cashfree webhook - automatically called when payment status changes
    When payment is successful: PENDING → PROCESSING
    """
    
    try:
        # Get raw body
        raw_body = await request.body()
        body_str = raw_body.decode('utf-8')
        
        print(f"[WEBHOOK] Received request")
        print(f"[WEBHOOK] Headers: {dict(request.headers)}")
        print(f"[WEBHOOK] Raw body: {body_str}")
        
        # Handle empty body
        if not body_str or body_str.strip() == "":
            print("[WEBHOOK] Empty body received")
            return {
                "status": "ignored", 
                "message": "Empty webhook body",
                "note": "This might be a test ping from Cashfree. No action needed."
            }
        
        # Try to parse JSON
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError as e:
            print(f"[WEBHOOK] JSON decode error: {str(e)}")
            print(f"[WEBHOOK] Body content: {body_str[:200]}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid JSON payload: {str(e)}"
            )
        
        # Verify webhook signature (if present)
        signature = request.headers.get("x-webhook-signature")
        timestamp = request.headers.get("x-webhook-timestamp")
        
        if signature and timestamp and CASHFREE_CLIENT_PAYMENT_SECRET:
            signed_payload = f"{timestamp}.{body_str}"
            computed_signature = hmac.new(
                CASHFREE_CLIENT_PAYMENT_SECRET.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(computed_signature, signature):
                print("[WEBHOOK] ❌ Invalid signature")
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
            
            print("[WEBHOOK] ✅ Signature verified")
        else:
            print("[WEBHOOK] ⚠️  No signature to verify (might be test webhook)")
        
        # Extract payment data
        # Cashfree sends different payload structures, handle both
        if "data" in payload:
            data = payload.get("data", {})
        else:
            data = payload  # Some webhooks send data directly
        
        link_id = data.get("link_id")
        link_status = data.get("link_status")
        
        print(f"[WEBHOOK] Parsed - link_id: {link_id}, status: {link_status}")
        
        if not link_id:
            print("[WEBHOOK] No link_id in payload")
            raise HTTPException(status_code=400, detail="Invalid webhook data: missing link_id")
        
        # Find order by cf_link_id stored in metadata
        orders = await Order.filter(
            metadata__contains=link_id
        ).prefetch_related('user', 'items__item__vendor')
        
        if not orders:
            print(f"[WEBHOOK] Order not found for link_id: {link_id}")
            # Try to extract order_id from link_id as fallback
            try:
                # Format: CF_ORD_12345678_ABC123
                parts = link_id.split("_")
                if len(parts) >= 3:
                    order_id = "_".join(parts[1:-1])
                    print(f"[WEBHOOK] Trying fallback order_id: {order_id}")
                    order = await Order.get_or_none(id=order_id).prefetch_related('user', 'items__item__vendor')
                    if order:
                        orders = [order]
            except Exception as e:
                print(f"[WEBHOOK] Fallback failed: {e}")
            
            if not orders:
                return {"status": "ignored", "message": "Order not found"}
        
        order = orders[0]
        print(f"[WEBHOOK] Found order: {order.id}")
        
        # Handle payment status
        if link_status == "PAID":
            print(f"[WEBHOOK] Processing PAID status for order {order.id}")
            
            # CRITICAL: Change status from PENDING to PROCESSING
            order.status = OrderStatus.PROCESSING
            order.payment_status = "paid"
            
            if order.metadata is None:
                order.metadata = {}
            
            if "cashfree" not in order.metadata:
                order.metadata["cashfree"] = {}
            
            order.metadata["cashfree"]["payment_status"] = "PAID"
            order.metadata["cashfree"]["paid_at"] = data.get("link_paid_at", datetime.utcnow().isoformat())
            order.metadata["cashfree"]["payment_amount"] = data.get("link_amount_paid")
            
            await order.save()
            
            print(f"[WEBHOOK] ✅ Payment successful - Order {order.id} status: PENDING → PROCESSING")
            
            # Send notifications
            try:
                notification_payload = {
                    "type": "payment_success",
                    "order_id": order.id,
                    "customer_name": order.user.name,
                    "amount": float(order.total),
                    "paid_at": data.get("link_paid_at"),
                    "status": "PROCESSING"
                }
                
                # WebSocket notifications
                await manager.send_to(notification_payload, "customers", str(order.user.id))
                
                # Notify customer
                await send_notification(
                    order.user.id,
                    "Payment Successful",
                    f"Your payment of ₹{order.total} was successful. Order #{order.id} is now being processed."
                )
                
                # Notify all vendors
                vendor_ids = set()
                for item in order.items:
                    vendor_ids.add(item.item.vendor_id)
                
                for vendor_id in vendor_ids:
                    vendor = await VendorProfile.get_or_none(id=vendor_id)
                    if vendor:
                        await manager.send_to(notification_payload, "vendors", str(vendor.user_id))
                        await send_notification(
                            vendor.user_id,
                            "New Paid Order",
                            f"New order #{order.id} received with confirmed payment."
                        )
                
                # Redis pub/sub
                if redis:
                    await redis.publish("order_updates", json.dumps(notification_payload))
                
                print("[WEBHOOK] ✅ Notifications sent")
                
            except Exception as e:
                print(f"[WEBHOOK] Notification error: {e}")
                import traceback
                traceback.print_exc()
            
        elif link_status == "FAILED":
            print(f"[WEBHOOK] Processing FAILED status for order {order.id}")
            
            order.payment_status = "failed"
            
            if order.metadata is None:
                order.metadata = {}
            
            if "cashfree" not in order.metadata:
                order.metadata["cashfree"] = {}
                
            order.metadata["cashfree"]["payment_status"] = "FAILED"
            order.metadata["cashfree"]["failed_at"] = data.get("link_failed_at", datetime.utcnow().isoformat())
            order.metadata["cashfree"]["failure_reason"] = data.get("failure_reason")
            
            await order.save()
            
            print(f"[WEBHOOK] ❌ Payment failed for order {order.id}")
            
            # Notify customer
            try:
                await send_notification(
                    order.user.id,
                    "Payment Failed",
                    f"Your payment for order #{order.id} failed. Please try again."
                )
            except Exception as e:
                print(f"[WEBHOOK] Notification error: {e}")
            
        elif link_status == "EXPIRED":
            print(f"[WEBHOOK] Processing EXPIRED status for order {order.id}")
            
            order.payment_status = "expired"
            
            if order.metadata is None:
                order.metadata = {}
            
            if "cashfree" not in order.metadata:
                order.metadata["cashfree"] = {}
                
            order.metadata["cashfree"]["payment_status"] = "EXPIRED"
            order.metadata["cashfree"]["expired_at"] = datetime.utcnow().isoformat()
            
            await order.save()
            
            print(f"[WEBHOOK] ⏰ Payment link expired for order {order.id}")
        
        else:
            print(f"[WEBHOOK] Unknown status: {link_status}")
        
        return {"status": "success", "message": "Webhook processed"}
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"[WEBHOOK ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return 200 to prevent Cashfree from retrying
        # But log the error
        return {
            "status": "error", 
            "message": str(e),
            "note": "Error logged but returning 200 to prevent retry"
        }


# ============================================================
# ADD: Test Webhook Endpoint
# ============================================================

# @router.get("/webhook/test")
# async def test_webhook(request: Request):
#     """
#     Test endpoint to simulate webhook calls.
#     Use this to test your webhook handler locally.
#     """
    
#     try:
#         raw_body = await request.body()
#         body_str = raw_body.decode('utf-8')
        
#         print(f"[TEST WEBHOOK] Body: {body_str}")
        
#         if not body_str:
#             return {"error": "Empty body"}
        
#         try:
#             payload = json.loads(body_str)
#             return {
#                 "status": "success",
#                 "message": "Test webhook received",
#                 "parsed_data": payload
#             }
#         except json.JSONDecodeError as e:
#             return {
#                 "error": "Invalid JSON",
#                 "details": str(e),
#                 "body": body_str[:200]
#             }
            
#     except Exception as e:
#         return {
#             "error": str(e),
#             "type": type(e).__name__
#         }

@router.get("/test/pay-last")
@router.post("/test/pay-last")
async def pay_last_order_no_auth():
    """
    TEST ONLY: Find and pay the most recent unpaid order.
    Just open in browser: /payment/test/pay-last
    
    ⚠️ REMOVE THIS ENDPOINT IN PRODUCTION!
    """
    
    # Find most recent unpaid order
    order = await Order.filter(
        payment_status="unpaid"
    ).order_by('-created_at').first().prefetch_related('user', 'items__item__vendor')
    
    if not order:
        return {
            "success": False,
            "message": "No unpaid orders found in the system"
        }
    
    # Update order
    old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    
    order.status = OrderStatus.PROCESSING
    order.payment_status = "paid"
    
    if order.metadata is None:
        order.metadata = {}
    
    if "cashfree" not in order.metadata:
        order.metadata["cashfree"] = {}
    
    order.metadata["cashfree"]["payment_status"] = "PAID"
    order.metadata["cashfree"]["paid_at"] = datetime.utcnow().isoformat()
    order.metadata["cashfree"]["payment_amount"] = float(order.total)
    order.metadata["cashfree"]["test_no_auth_last"] = True
    
    await order.save()
    
    print(f"[NO-AUTH LAST] ✅ Order {order.id}: {old_status} → PROCESSING")
    
    # Send notifications
    try:
        await send_notification(
            order.user.id,
            "Payment Successful (TEST)",
            f"Order #{order.id} payment confirmed."
        )
    except Exception as e:
        print(f"[NO-AUTH LAST] Notification error: {e}")
    
    return {
        "success": True,
        "message": "✅ Most recent order marked as paid!",
        "order_id": order.id,
        "customer_name": order.user.name,
        "old_status": old_status,
        "new_status": "processing",
        "payment_status": "paid",
        "total": float(order.total),
        "order_date": order.order_date.isoformat(),
        "note": "⚠️ This is a TEST payment - remove this endpoint in production!"
    }


    return {
        "success": True,
        "message": "Last order marked as paid",
        "order_id": order.id,
        "old_status": old_status,
        "new_status": "processing",
        "total": float(order.total)
    }


@router.get("/verify/{order_id}")
async def verify_payment_status(order_id: str):
    """
    Manually verify payment status and update order if needed.
    This is a backup in case webhook fails.
    """
    
    order = await Order.get_or_none(id=order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get cf_link_id from order metadata
    cashfree_data = order.metadata.get("cashfree", {}) if order.metadata else {}
    cf_link_id = cashfree_data.get("cf_link_id")
    
    if not cf_link_id:
        raise HTTPException(status_code=400, detail="No Cashfree link found for this order")
    
    # Call Cashfree API to check link status
    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{CASHFREE_BASE}/links/{cf_link_id}",
                headers=headers
            )
            
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Failed to verify payment: {resp.text}"
                )
            
            data = resp.json()
            link_status = data.get("link_status")
            
            # Update order if payment was successful but status not updated
            if link_status == "PAID" and order.payment_status != "paid":
                order.status = OrderStatus.PROCESSING  # PENDING → PROCESSING
                order.payment_status = "paid"
                
                if order.metadata:
                    order.metadata["cashfree"]["payment_status"] = "PAID"
                    order.metadata["cashfree"]["paid_at"] = data.get("link_paid_at")
                
                await order.save()
                
                print(f"[VERIFY] ✅ Order {order_id} status updated: PENDING → PROCESSING")
            
            return {
                "order_id": order_id,
                "link_status": link_status,
                "payment_status": order.payment_status,
                "order_status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                "amount_paid": data.get("link_amount_paid"),
                "paid_at": data.get("link_paid_at")
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying payment: {str(e)}")