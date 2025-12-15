# ============================================================
# MULTI-ORDER PAYMENT LINK - routes/payment/routes.py
# ============================================================
import base64
from decimal import Decimal
import hashlib
import hmac
from fastapi import APIRouter, Header, Query, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime
from applications.user.vendor import VendorProfile
from app.redis import get_redis
from routes.payment.payment_verification import verify_payment_status
from routes.rider.notifications import send_notification
import httpx
import uuid
from applications.customer.models import Order, OrderStatus
from app.config import settings

CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"

# ============================================================
# SCHEMAS
# ============================================================

router = APIRouter()


class PaymentWebhookData(BaseModel):
    """Cashfree Payment Webhook Data"""
    order_id: str
    cf_order_id: Optional[str] = None
    order_amount: float
    order_status: str  # SUCCESS, FAILED, CANCELLED, etc.
    payment_status: str
    payment_time: Optional[str] = None
    payment_group: Optional[str] = None
    payment_method: Optional[str] = None


# ----------------------------------
# CALLBACK (Return URL After Payment)
# ----------------------------------
@router.get("/callback")
async def payment_callback(
    order_id: str = Query(...),
    order_status: Optional[str] = Query(None),
    redis = Depends(get_redis)
):
    """
    Called when user returns after payment.
    We verify via Cashfree API & update DB.
    """
    try:
        print(f"[CALLBACK] Received for: {order_id}")

        # Verify with Cashfree API
        verification = await verify_payment_status(order_id)
        if not verification.get("success"):
            return {"success": False, "message": "Verification failed"}

        cf_status = verification.get("order_status")
        print(f"[CALLBACK] Cashfree status: {cf_status}")

        # Fetch orders with this parent_order_id
        orders = await Order.filter(parent_order_id=order_id).prefetch_related("user")
        if not orders:
            return {"success": False, "message": "Orders not found"}

        # Update orders if paid
        if cf_status == "PAID":
            for order in orders:
                order.payment_status = "paid"
                order.status = OrderStatus.PROCESSING
                await order.save()

                # Send customer + vendor notifications
                payload = {
                    "type": "order_placed",
                    "order_id": order.id,
                    "parent_order_id": order_id,
                    "customer_name": order.user.name if order.user else "Customer",
                    "payment_method": "Cashfree",
                    "payment_status": "paid",
                    "order_status": "PROCESSING",
                    "created_at": datetime.utcnow().isoformat()
                }

                try:
                    await redis.publish("order_updates", json.dumps(payload))
                    vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                    if vendor:
                        await send_notification(
                            vendor.user_id,
                            "New Paid Order",
                            f"Order #{order.id} paid successfully"
                        )
                except Exception as e:
                    print(f"[CALLBACK] Notification error: {e}")

            return {"success": True, "message": "Orders marked paid via callback"}

        # Pending / expired / unknown
        return {
            "success": False,
            "order_id": order_id,
            "order_status": cf_status
        }

    except Exception as e:
        print(f"[CALLBACK] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------
# WEBHOOK (Server-to-Server)
# ----------------------------------
@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_webhook_signature: str = Header(None),
    x_webhook_timestamp: str = Header(None),
    redis = Depends(get_redis)
):
    """
    Cashfree webhook — must verify signature before processing.
    """
    try:
        raw_body = await request.body()

        # Signature verification (required for production) :contentReference[oaicite:1]{index=1}
        secret = settings.CASHFREE_CLIENT_PAYMENT_SECRET.encode()
        data_to_sign = x_webhook_timestamp.encode() + raw_body
        expected_sig = base64.b64encode(hmac.new(secret, data_to_sign, hashlib.sha256).digest()).decode()

        if expected_sig != x_webhook_signature:
            print("[WEBHOOK] ❌ Signature mismatch!")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

        # Parse JSON
        body = json.loads(raw_body)
        data = body.get("data", {})
        order_data = data.get("order", {})
        payment_data = data.get("payment", {})

        parent_order_id = order_data.get("order_id")
        if not parent_order_id:
            return {"status": "error", "message": "Missing order_id"}

        # Verify payment with Cashfree API
        verification = await verify_payment_status(parent_order_id)
        if not verification.get("success"):
            return {"status": "error", "message": "Verification failed"}

        cf_status = verification.get("order_status")
        print(f"[WEBHOOK] Verified status: {cf_status}")

        if cf_status == "PAID":
            orders = await Order.filter(parent_order_id=parent_order_id).prefetch_related("user")
            for order in orders:
                order.payment_status = "paid"
                order.status = OrderStatus.PROCESSING
                order.transaction_id = payment_data.get("cf_payment_id")
                await order.save()

                # Notifications
                payload = {
                    "type": "order_placed",
                    "order_id": order.id,
                    "parent_order_id": parent_order_id,
                    "customer_name": order.user.name if order.user else "Customer",
                    "payment_method": "Cashfree",
                    "payment_status": "paid",
                    "order_status": "PROCESSING",
                    "created_at": datetime.utcnow().isoformat()
                }
                try:
                    await redis.publish("order_updates", json.dumps(payload))
                    vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                    if vendor:
                        await send_notification(
                            vendor.user_id,
                            "New Paid Order",
                            f"Order #{order.id} paid"
                        )
                except Exception as e:
                    print(f"[WEBHOOK] Notification error: {e}")

            return {"status": "success", "message": "Orders updated (webhook)"}

        return {"status": "success", "message": f"No action for status {cf_status}"}

    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ----------------------------------
# MANUAL VERIFY ENDPOINT
# ----------------------------------
@router.get("/verify/{parent_order_id}")
async def verify_payment_endpoint(parent_order_id: str):
    """
    Manual verify (for app or debugging)
    """
    try:
        result = await verify_payment_status(parent_order_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail="Verification failed")

        return {
            "success": True,
            "parent_order_id": parent_order_id,
            "order_status": result.get("order_status"),
            "cf_order_id": result.get("cf_order_id"),
            "order_amount": result.get("order_amount"),
            "payment_session_id": result.get("payment_session_id")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/test/pay-last")
@router.post("/test/pay-last")
async def pay_last_order_no_auth():
    """
    Test endpoint to mark the most recent unpaid order(s) as paid.
    This simulates successful payment for testing purposes.
    
    ⚠️ REMOVE THIS ENDPOINT IN PRODUCTION!
    """
    
    print("=" * 60)
    print("🧪 TEST PAYMENT ENDPOINT CALLED")
    print("=" * 60)
    
    # Find the most recent unpaid order
    order = await Order.filter(
        payment_status="unpaid"
    ).order_by('-created_at').first().prefetch_related('user')
    
    if not order:
        return {
            "success": False,
            "message": "No unpaid orders found in the system"
        }
    
    print(f"📦 Found unpaid order: {order.id}")
    print(f"   Parent Order ID: {order.parent_order_id}")
    print(f"   Status: {order.status}")
    print(f"   Payment Status: {order.payment_status}")
    
    # Check if this order has a parent_order_id (combined payment)
    orders_to_process = [order]
    is_combined = False
    
    if order.parent_order_id:
        is_combined = True
        print(f"🔗 This is a combined payment with parent_order_id: {order.parent_order_id}")
        
        # Fetch all orders with the same parent_order_id
        orders_to_process = await Order.filter(
            parent_order_id=order.parent_order_id
        ).prefetch_related('user')
        
        print(f"   Found {len(orders_to_process)} orders in this payment group")
    else:
        print(f"📦 Single order payment (no parent_order_id)")
    
    # Process all orders
    processed_orders = []
    total_amount = Decimal("0")
    
    for ord in orders_to_process:
        old_status = ord.status.value if hasattr(ord.status, 'value') else str(ord.status)
        old_payment_status = ord.payment_status
        
        # Update order status
        ord.status = OrderStatus.PROCESSING
        ord.payment_status = "paid"
        ord.transaction_id = f"TEST_TXN_{uuid.uuid4().hex[:8].upper()}"
        
        # Update metadata
        if ord.metadata is None:
            ord.metadata = {}
        
        ord.metadata["test_payment"] = {
            "paid_at": datetime.utcnow().isoformat(),
            "payment_amount": float(ord.total),
            "test_endpoint": True,
            "note": "⚠️ This is a TEST payment"
        }
        
        await ord.save()
        
        total_amount += ord.total
        
        print(f"✅ Order {ord.id} updated:")
        print(f"   Status: {old_status} → PROCESSING")
        print(f"   Payment: {old_payment_status} → paid")
        
        # Send notification to customer
        try:
            if ord.user:
                await send_notification(
                    ord.user.id,
                    "Payment Successful (TEST)",
                    f"Order #{ord.id} payment confirmed via test endpoint."
                )
                print(f"   📧 Notification sent to user {ord.user.id}")
        except Exception as e:
            print(f"   ⚠️ Notification error: {e}")
        
        # Send notification to vendor
        try:
            from applications.vendor.models import VendorProfile
            vendor = await VendorProfile.get_or_none(id=ord.vendor_id)
            if vendor:
                await send_notification(
                    vendor.user_id,
                    "New Paid Order (TEST)",
                    f"Order #{ord.id} received and paid via test endpoint."
                )
                print(f"   📧 Notification sent to vendor {vendor.user_id}")
        except Exception as e:
            print(f"   ⚠️ Vendor notification error: {e}")
        
        processed_orders.append({
            "order_id": ord.id,
            "old_status": old_status,
            "new_status": "PROCESSING",
            "old_payment_status": old_payment_status,
            "new_payment_status": "paid",
            "total": float(ord.total)
        })
    
    print("=" * 60)
    print(f"✅ TEST PAYMENT COMPLETED: {len(processed_orders)} order(s) marked as paid")
    print("=" * 60)
    
    # Prepare response
    response = {
        "success": True,
        "message": f"✅ {len(processed_orders)} order(s) marked as paid!",
        "orders_count": len(processed_orders),
        "total_amount": float(total_amount),
        "is_combined_payment": is_combined,
        "parent_order_id": order.parent_order_id if is_combined else None,
        "processed_orders": processed_orders,
        "customer_name": order.user.name if order.user else "Unknown",
        "note": "⚠️ This is a TEST payment endpoint - REMOVE IN PRODUCTION!"
    }
    
    return response


@router.get("/test/orders-status")
async def get_orders_status():
    """
    Test endpoint to check status of recent orders.
    Useful for debugging.
    """
    
    orders = await Order.all().order_by('-created_at').limit(10).prefetch_related('user')
    
    orders_data = []
    for order in orders:
        orders_data.append({
            "order_id": order.id,
            "parent_order_id": order.parent_order_id,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "payment_status": order.payment_status,
            "total": float(order.total),
            "customer": order.user.name if order.user else "Unknown",
            "created_at": order.created_at.isoformat()
        })
    
    return {
        "success": True,
        "total_orders": len(orders_data),
        "orders": orders_data
    }    