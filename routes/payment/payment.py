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
from app.token import get_current_user
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.redis import get_redis
from routes.payment.payment_verification import verify_payment_status
from routes.rider.notifications import send_notification, NotificationIn  # Add NotificationIn
import httpx
import uuid
from applications.customer.models import Order, OrderStatus
from app.config import settings
from app.utils.websocket_manager import manager

CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"

# ============================================================
# SCHEMAS
# ============================================================

router = APIRouter(prefix="/payment", tags=["payment"])

current_user = Depends(get_current_user)


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
    


class PaymentConfirmRequest(BaseModel):
    """Request model for payment confirmation from Flutter app"""
    parent_order_id: str
    


@router.post("/confirm")
async def confirm_payment_from_app(
    request: PaymentConfirmRequest,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    Confirm payment from Flutter app after redirect.
    Hits Cashfree API to verify payment status first.
    Marks orders as paid & processing only if payment is confirmed.
    """

    parent_order_id = request.parent_order_id

    try:
        # 1️⃣ Verify payment with Cashfree
        verification_result = await verify_payment_status(parent_order_id)
        if not verification_result.get("success"):
            raise HTTPException(status_code=400, detail="Payment verification failed")

        cashfree_status = verification_result.get("order_status")

        # 2️⃣ Fetch orders for this parent_order_id
        orders = await Order.filter(parent_order_id=parent_order_id).prefetch_related("user")
        if not orders:
            raise HTTPException(status_code=404, detail="Orders not found")

        # 3️⃣ If payment is PAID, mark orders & notify
        if cashfree_status == "PAID":
            for order in orders:
                # Idempotency check
                if order.payment_status == "paid":
                    continue

                order.payment_status = "paid"
                order.status = OrderStatus.PROCESSING
                await order.save()

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
                    # Redis publish
                    await redis.publish("order_updates", json.dumps(payload))

                    # Vendor notification
                    vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                    if vendor:
                        await send_notification(
                            vendor.user_id,
                            "New Paid Order",
                            f"Order #{order.id} paid successfully"
                        )
                except Exception as e:
                    print(f"[CONFIRM] Notification error: {e}")

            return {
                "success": True,
                "message": "Orders marked paid",
                "parent_order_id": parent_order_id,
                "orders_count": len(orders),
                "cashfree_status": cashfree_status,
                "cashfree_response": verification_result
            }

        # 4️⃣ If payment NOT PAID → return status
        return {
            "success": False,
            "message": f"Payment not completed. Status: {cashfree_status}",
            "parent_order_id": parent_order_id,
            "orders_count": len(orders),
            "cashfree_status": cashfree_status,
            "cashfree_response": verification_result
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CONFIRM] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{parent_order_id}")
async def get_payment_status(
    parent_order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Flutter app can poll this endpoint to check payment status.
    
    Usage from Flutter:
    GET /api/payment/status/ORDER_77A8641A732B
    """
    
    print(f"🔍 Payment status check for: {parent_order_id}")
    
    # Find orders
    orders = await Order.filter(
        parent_order_id=parent_order_id,
        user_id=current_user.id
    ).all()
    
    if not orders:
        raise HTTPException(
            status_code=404,
            detail="Orders not found"
        )
    
    # Verify with Cashfree
    verification_result = await verify_payment_status(parent_order_id)
    
    if not verification_result.get("success"):
        return {
            "success": False,
            "message": "Unable to verify payment status",
            "parent_order_id": parent_order_id
        }
    
    cashfree_status = verification_result.get("order_status")
    
    # Get current order statuses
    orders_info = [
        {
            "order_id": order.id,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "payment_status": order.payment_status,
            "total": float(order.total)
        }
        for order in orders
    ]
    
    return {
        "success": True,
        "parent_order_id": parent_order_id,
        "cashfree_status": cashfree_status,
        "orders_count": len(orders),
        "orders": orders_info,
        "is_paid": cashfree_status == "PAID",
        "needs_processing": cashfree_status == "PAID" and orders[0].payment_status != "paid"
    }


@router.post("/retry-confirmation/{parent_order_id}")
async def retry_payment_confirmation(
    parent_order_id: str,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    Retry payment confirmation if webhook failed or app didn't confirm.
    Flutter app can call this if user reports payment success but orders not updated.
    
    Usage from Flutter:
    POST /api/payment/retry-confirmation/ORDER_77A8641A732B
    """
    
    print(f"🔄 Retrying payment confirmation for: {parent_order_id}")
    
    # Find orders
    orders = await Order.filter(
        parent_order_id=parent_order_id,
        user_id=current_user.id
    ).prefetch_related("user")
    
    if not orders:
        raise HTTPException(
            status_code=404,
            detail="Orders not found"
        )
    
    # Check if already processed
    if orders[0].payment_status == "paid":
        return {
            "success": True,
            "message": "Orders are already marked as paid",
            "parent_order_id": parent_order_id,
            "orders_count": len(orders)
        }
    
    # Verify with Cashfree
    verification_result = await verify_payment_status(parent_order_id)
    
    if not verification_result.get("success"):
        raise HTTPException(
            status_code=400,
            detail="Unable to verify payment with Cashfree"
        )
    
    cashfree_status = verification_result.get("order_status")
    
    if cashfree_status == "PAID":
        # Process payment confirmation
        for order in orders:
            order.payment_status = "paid"
            order.status = OrderStatus.PROCESSING
            
            if order.metadata is None:
                order.metadata = {}
            
            order.metadata["payment_retry"] = {
                "retried_at": datetime.utcnow().isoformat(),
                "user_id": str(current_user.id)
            }
            
            await order.save()
            
            # Notify vendor
            try:
                vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                if vendor:
                    await send_notification(
                        vendor.user_id,
                        "New Paid Order",
                        f"Order #{order.id} received and paid"
                    )
            except Exception as e:
                print(f"Notification error: {e}")
        
        return {
            "success": True,
            "message": "Payment confirmed successfully!",
            "parent_order_id": parent_order_id,
            "orders_count": len(orders),
            "verified_status": cashfree_status
        }
    else:
        return {
            "success": False,
            "message": f"Payment not confirmed. Status: {cashfree_status}",
            "parent_order_id": parent_order_id,
            "verified_status": cashfree_status
        }


# routes.payment.payment.py
# Fix for @router.post("/test/pay-last")

# routes.payment.payment.py
# CORRECTED VERSION - Matches your WebSocket manager structure

@router.get("/test/pay-last")
@router.post("/test/pay-last")
async def pay_last_order_no_auth(redis = Depends(get_redis)):
    """
    Test endpoint to mark last unpaid order as paid
    Sends proper notifications to customer and vendor
    """
    
    order = await Order.filter(
        payment_status="unpaid"
    ).order_by('-created_at').first().prefetch_related('user')
    
    if not order:
        return {
            "success": False,
            "message": "No unpaid orders found in the system"
        }

    # Get all orders in payment group
    orders_to_process = [order]
    is_combined = False
    
    if order.parent_order_id:
        is_combined = True
        orders_to_process = await Order.filter(
            parent_order_id=order.parent_order_id
        ).prefetch_related('user')
    
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
        
        # 🔥 FIX: Send notifications to CUSTOMER
        try:
            if ord.user_id:
                # WebSocket notification (sends to notification channel)
                await manager.send_notification(
                    to_type="customers",
                    to_id=str(ord.user_id),
                    title="Payment Successful",
                    body=f"Your payment for order #{ord.id} is confirmed!",
                    data={
                        "order_id": ord.id,
                        "parent_order_id": ord.parent_order_id,
                        "total": float(ord.total),
                        "status": "PROCESSING"
                    },
                    urgency="normal"
                )
                
                # Push notification (Firebase)
                from routes.rider.notifications import NotificationIn
                await send_notification(NotificationIn(
                    user_id=ord.user_id,
                    title="Payment Successful",
                    body=f"Order #{ord.id} payment confirmed."
                ))
                
                # Redis publish for real-time updates
                customer_payload = {
                    "type": "payment_success",
                    "order_id": ord.id,
                    "parent_order_id": ord.parent_order_id,
                    "total": float(ord.total),
                    "status": "PROCESSING",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await redis.publish("order_updates", json.dumps(customer_payload))
                
                print(f"   📧 Customer notifications sent to user {ord.user_id}")
        except Exception as e:
            print(f"   ⚠️ Customer notification error: {e}")
        
        # 🔥 FIX: Send notifications to VENDOR
        try:
            from applications.user.vendor import VendorProfile
            vendor = await VendorProfile.get_or_none(id=ord.vendor_id)
            
            if vendor:
                # WebSocket notification (sends to notification channel)
                await manager.send_notification(
                    to_type="vendors",
                    to_id=str(vendor.user_id),
                    title="New Paid Order",
                    body=f"Order #{ord.id} received and paid. Total: ₹{ord.total}",
                    data={
                        "order_id": ord.id,
                        "parent_order_id": ord.parent_order_id,
                        "customer_id": ord.user_id,
                        "total": float(ord.total)
                    },
                    urgency="normal"
                )
                
                # Push notification (Firebase)
                from routes.rider.notifications import NotificationIn
                await send_notification(NotificationIn(
                    user_id=vendor.user_id,
                    title="New Paid Order",
                    body=f"Order #{ord.id} received and paid."
                ))
                
                # Redis publish
                vendor_payload = {
                    "type": "new_paid_order",
                    "order_id": ord.id,
                    "parent_order_id": ord.parent_order_id,
                    "customer_id": ord.user_id,
                    "total": float(ord.total),
                    "timestamp": datetime.utcnow().isoformat()
                }
                await redis.publish("vendor_orders", json.dumps(vendor_payload))
                
                print(f"   📧 Vendor notifications sent to user {vendor.user_id}")
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
    
    response = {
        "success": True,
        "message": f"✅ {len(processed_orders)} order(s) marked as paid with notifications!",
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


class PhonePeStatusRequest(BaseModel):
    merchantOrderId: str
    token: str


@router.post("/phonepe/status")
async def get_phonepe_status(
    req_data: PhonePeStatusRequest,
    redis = Depends(get_redis)
):
    """
    Check PhonePe payment status and mark orders as paid if COMPLETED.
    """
    url = f"https://api-preprod.phonepe.com/apis/pg-sandbox/checkout/v2/order/{req_data.merchantOrderId}/status?details=false"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"O-Bearer {req_data.token}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            print(f"PhonePe Status Response for {req_data.merchantOrderId}: {response.text}")
            
            if response.status_code != 200:
                return response.json()
                
            resp_data = response.json()
            
            # If payment is COMPLETED, process the orders
            if resp_data.get("state") == "COMPLETED":
                parent_order_id = req_data.merchantOrderId
                orders = await Order.filter(parent_order_id=parent_order_id).prefetch_related("user")
                
                if orders:
                    for order in orders:
                        # Only update if not already paid
                        if order.payment_status != "paid":
                            order.payment_status = "paid"
                            order.status = OrderStatus.PROCESSING
                            order.transaction_id = f"PHONEPE_{resp_data.get('orderId')}"
                            await order.save()
                            
                            # 1. Notify Customer
                            try:
                                # WebSocket
                                await manager.send_notification(
                                    to_type="customers",
                                    to_id=str(order.user_id),
                                    title="Payment Successful",
                                    body=f"Your PhonePe payment for order #{order.id} is confirmed!",
                                    data={"order_id": order.id, "total": float(order.total), "status": "PROCESSING"}
                                )
                                # Push
                                await send_notification(NotificationIn(
                                    user_id=order.user_id,
                                    title="Payment Successful",
                                    body=f"Order #{order.id} payment confirmed via PhonePe."
                                ))
                                # Redis
                                customer_payload = {
                                    "type": "payment_success",
                                    "order_id": order.id,
                                    "parent_order_id": parent_order_id,
                                    "payment_method": "PhonePe",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                                await redis.publish("order_updates", json.dumps(customer_payload))
                            except Exception as e:
                                print(f"Customer notification error: {e}")
                                
                            # 2. Notify Vendor
                            try:
                                vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                                if vendor:
                                    # WebSocket
                                    await manager.send_notification(
                                        to_type="vendors",
                                        to_id=str(vendor.user_id),
                                        title="New Paid Order (PhonePe)",
                                        body=f"Order #{order.id} received and paid via PhonePe. Total: ₹{order.total}",
                                        data={"order_id": order.id, "customer_id": order.user_id, "total": float(order.total)}
                                    )
                                    # Push
                                    await send_notification(NotificationIn(
                                        user_id=vendor.user_id,
                                        title="New Paid Order",
                                        body=f"Order #{order.id} received and paid via PhonePe."
                                    ))
                                    # Redis
                                    vendor_payload = {
                                        "type": "new_paid_order",
                                        "order_id": order.id,
                                        "parent_order_id": parent_order_id,
                                        "payment_method": "PhonePe",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                                    await redis.publish("vendor_orders", json.dumps(vendor_payload))
                            except Exception as e:
                                print(f"Vendor notification error: {e}")
                                
                    print(f"✅ orders with parent_order_id {parent_order_id} marked as paid via PhonePe")
            
            return resp_data
            
    except Exception as e:
        print(f"Error checking PhonePe status: {e}")
        raise HTTPException(status_code=500, detail=f"PhonePe status check error: {str(e)}")
