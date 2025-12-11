from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import hmac
import hashlib
import json
from datetime import datetime
from applications.customer.models import Order, OrderStatus
from app.config import settings
# Get your secret from settings
CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"



# routes.webhooks.cashfree.py

router = APIRouter(prefix="/cashfree", tags=["Cashfree"])

@router.get("/payment")
@router.post("/payment")
async def cashfree_payment_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None)
):
    try:
        raw_body = await request.body()
        body_str = raw_body.decode('utf-8')
        
        # Handle empty body
        if not body_str or body_str.strip() == "":
            print("[WEBHOOK] Empty body received")
            return {"success": True, "message": "Empty webhook received"}
        
        # Try to parse JSON
        try:
            webhook_data = json.loads(body_str)
        except json.JSONDecodeError as je:
            print(f"[WEBHOOK] JSON parse error: {str(je)}")
            print(f"[WEBHOOK] Raw body: {body_str[:200]}")
            return {"success": False, "message": "Invalid JSON"}
        
        print(f"[WEBHOOK] Received: {json.dumps(webhook_data, indent=2)}")
        
        webhook_type = webhook_data.get("type")
        data = webhook_data.get("data", {})
        
        payment = data.get("payment", {})
        payment_status = payment.get("payment_status")
        cf_payment_id = payment.get("cf_payment_id")
        
        order_info = data.get("order", {})
        order_meta = order_info.get("order_meta", {})
        order_ids = order_meta.get("order_ids", [])
        
        if not order_ids:
            order_id = order_info.get("order_id")
            if order_id:
                order_ids = [order_id]
        
        print(f"[WEBHOOK] Type: {webhook_type}, Status: {payment_status}, Orders: {order_ids}")
        
        if webhook_type == "PAYMENT_SUCCESS_WEBHOOK" and payment_status == "SUCCESS":
            updated_orders = []
            
            for order_id in order_ids:
                order = await Order.get_or_none(id=order_id)
                
                if not order:
                    print(f"[WEBHOOK] Order {order_id} not found")
                    continue
                
                old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
                
                if old_status.lower() == "pending":
                    order.status = OrderStatus.PROCESSING
                    order.payment_status = "paid"
                    
                    if order.metadata is None:
                        order.metadata = {}
                    if "cashfree" not in order.metadata:
                        order.metadata["cashfree"] = {}
                    
                    order.metadata["cashfree"].update({
                        "payment_status": "SUCCESS",
                        "paid_at": datetime.utcnow().isoformat(),
                        "cf_payment_id": cf_payment_id
                    })
                    
                    await order.save()
                    
                    print(f"[WEBHOOK] ✅ Order {order_id}: {old_status} → PROCESSING")
                    updated_orders.append(order_id)
            
            return {
                "success": True,
                "message": f"{len(updated_orders)} order(s) updated",
                "updated_orders": updated_orders
            }
        
        return {"success": True, "message": f"Webhook {webhook_type} received"}
    
    except Exception as e:
        print(f"[WEBHOOK] Error: {str(e)}")
        import traceback
        print(f"[WEBHOOK] Traceback: {traceback.format_exc()}")
        return {"success": False, "message": str(e)}