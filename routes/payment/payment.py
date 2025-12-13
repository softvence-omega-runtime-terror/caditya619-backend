# ============================================================
# MULTI-ORDER PAYMENT LINK - routes/payment/routes.py
# ============================================================
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime
from applications.user.vendor import VendorProfile
from app.redis import get_redis
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




@router.post("/webhook")
async def payment_webhook(
    request: Request,
    redis = Depends(get_redis)
):
    """
    Cashfree payment webhook endpoint.
    Called by Cashfree when payment status changes.
    
    Documentation: https://docs.cashfree.com/reference/webhook
    """
    try:
        # Get webhook data
        body = await request.json()
        print(f"📩 Received payment webhook: {json.dumps(body, indent=2)}")
        
        # Extract data from webhook
        data = body.get("data", {})
        order_data = data.get("order", {})
        payment_data = data.get("payment", {})
        
        cf_order_id = order_data.get("cf_order_id") or order_data.get("order_id")
        order_status = payment_data.get("payment_status", "").upper()
        
        if not cf_order_id:
            print("⚠️ No cf_order_id in webhook")
            return {"status": "error", "message": "Missing order ID"}
        
        print(f"Processing payment for cf_order_id: {cf_order_id}")
        print(f"Payment Status: {order_status}")
        
        # Find all orders with this cf_order_id
        orders = await Order.filter(cf_order_id=cf_order_id).prefetch_related("user")
        
        if not orders:
            print(f"⚠️ No orders found with cf_order_id: {cf_order_id}")
            return {"status": "error", "message": "Order not found"}
        
        print(f"Found {len(orders)} order(s) to update")
        
        # Handle payment status
        if order_status == "SUCCESS":
            # Update all orders to PROCESSING and mark as paid
            for order in orders:
                order.payment_status = "paid"
                order.status = OrderStatus.PROCESSING
                order.transaction_id = payment_data.get("cf_payment_id")
                await order.save()
                
                print(f"✅ Order {order.id} marked as PAID and PROCESSING")
                
                # Send notifications
                payload = {
                    "type": "order_placed",
                    "order_id": order.id,
                    "customer_name": order.user.name if order.user else "Customer",
                    "payment_method": "Cashfree",
                    "payment_status": "paid",
                    "created_at": datetime.utcnow().isoformat()
                }
                
                try:
                    # Publish to Redis
                    await redis.publish("order_updates", json.dumps(payload))
                    
                    # Send to customer via WebSocket (if you have websocket manager)
                    # await manager.send_to(payload, "customers", str(order.user_id), "notifications")
                    
                    # Notify vendor
                    vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                    if vendor:
                        # await manager.send_to(payload, "vendors", str(vendor.user_id), "notifications")
                        await send_notification(
                            vendor.user_id,
                            "New Paid Order",
                            f"New order #{order.id} received and paid"
                        )
                        print(f"📧 Vendor notified for order {order.id}")
                        
                except Exception as e:
                    print(f"⚠️ Notification error for order {order.id}: {e}")
            
            return {
                "status": "success",
                "message": f"{len(orders)} order(s) updated successfully"
            }
            
        elif order_status in ["FAILED", "CANCELLED", "USER_DROPPED"]:
            # Mark orders as failed
            for order in orders:
                order.payment_status = "failed" if order_status == "FAILED" else "cancelled"
                await order.save()
                print(f"❌ Order {order.id} payment {order.payment_status}")
            
            return {
                "status": "success",
                "message": f"Payment {order_status.lower()} recorded"
            }
        
        else:
            print(f"⚠️ Unhandled payment status: {order_status}")
            return {"status": "success", "message": "Status noted"}
    
    except Exception as e:
        print(f"⚠️ Webhook processing error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.get("/verify/{cf_order_id}")
async def verify_payment(cf_order_id: str):
    """
    Manually verify payment status by calling Cashfree API.
    Useful for debugging or manual verification.
    """
    headers = {
        "x-api-version": "2023-08-01",
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{CASHFREE_BASE}/orders/{cf_order_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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