from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, validator
from typing import List, Optional
import httpx
import uuid
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException, Body
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.redis import get_redis
from applications.customer.models import Order, OrderStatus
from app.config import settings
from routes.rider.notifications import send_notification
from app.utils.websocket_manager import manager
from fastapi import APIRouter, Request
from typing import Optional


CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"



router = APIRouter(prefix='/payment', tags=['Payment'])



@router.post("/test/webhook")
async def cashfree_test_webhook(request: Request):
    """
    Test webhook endpoint for payment providers (e.g. Cashfree).
    Expected JSON: { "link_id": "...", "payment_id": "...", "status": "SUCCESS" , "order_id": "..." }
    Behavior:
      - If payment indicates success, parent order.payment_status -> "paid" and parent order.status -> "paid"
      - All sub-orders for that parent will have status -> OrderStatus.PROCESSING and payment_status -> "paid"
      - Raw payload saved to order.metadata.cashfree.webhook_last for debugging
    """
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = dict(request.query_params) or {}

    link_id = payload.get("link_id") or payload.get("linkId") or payload.get("cf_order_id") or payload.get("orderId")
    payment_id = payload.get("payment_id") or payload.get("paymentId") or payload.get("cf_payment_id")
    tx_status = payload.get("status") or payload.get("tx_status") or payload.get("txStatus") or payload.get("link_status") or ""

    # treat common success tokens as success
    success_tokens = {"SUCCESS", "SUCCESSFUL", "PAID", "OK", "TXN_SUCCESS", "CAPTURED", "COMPLETED"}
    is_success = str(tx_status).upper() in success_tokens

    # Try to locate the parent order:
    order = None
    # direct id match if provided
    if payload.get("order_id") or payload.get("orderId"):
        oid = payload.get("order_id") or payload.get("orderId")
        order = await Order.get_or_none(id=oid)
    # try link_id match in recent orders metadata
    if order is None and link_id:
        recent = await Order.filter().order_by("-created_at").limit(200)
        for o in recent:
            if o.metadata and "cashfree" in o.metadata:
                cf = o.metadata["cashfree"]
                if str(cf.get("cf_link_id", "")).lower() == str(link_id).lower():
                    order = o
                    break

    if order is None:
        return JSONResponse({"success": False, "message": "Order not found for webhook payload", "payload": payload}, status_code=404)

    # ensure sub_orders relation loaded
    try:
        await order.fetch_related("sub_orders")
    except Exception:
        # best-effort; continue even if relation not prefetchable
        pass

    # Persist raw webhook payload
    if order.metadata is None:
        order.metadata = {}
    order.metadata.setdefault("cashfree", {})
    order.metadata["cashfree"]["webhook_last"] = {
        "received_at": datetime.utcnow().isoformat(),
        "payload": payload
    }

    if is_success:
        # update parent order
        order.payment_status = "paid"
        # try to set enum OrderStatus.PAID, fallback to string "paid"
        try:
            order.status = OrderStatus.PAID
        except Exception:
            try:
                # some setups may expect PROCESSING for parent; keep explicit "paid" string as last resort
                order.status = "paid"
            except Exception:
                pass

        # mark payment meta
        order.metadata["cashfree"]["payment_status"] = "PAID"
        if payment_id:
            order.metadata["cashfree"]["cf_payment_id"] = payment_id

        # update and save parent
        try:
            await order.save(update_fields=["status", "payment_status", "metadata"])
        except Exception:
            # fallback: save without update_fields
            await order.save()

        # update sub-orders: set to processing + paid
        updated_subs = []
        subs = getattr(order, "sub_orders", []) or []
        for sub in subs:
            try:
                sub.payment_status = "paid"
                try:
                    sub.status = OrderStatus.PROCESSING
                except Exception:
                    sub.status = "processing"
                if sub.metadata is None:
                    sub.metadata = {}
                sub.metadata.setdefault("cashfree", {})
                sub.metadata["cashfree"]["payment_status"] = "PAID"
                if payment_id:
                    sub.metadata["cashfree"]["cf_payment_id"] = payment_id
                await sub.save(update_fields=["status", "payment_status", "metadata"])
                updated_subs.append(sub.id if hasattr(sub, "id") else None)
            except Exception as e:
                print(f"[WEBHOOK] failed to update sub-order {getattr(sub,'id', None)}: {e}")

        return {"success": True, "message": "Payment recorded (TEST). Parent marked paid; sub-orders set to processing.", "parent_order": order.id, "updated_sub_orders": updated_subs}

    # non-successful payment -> store payload and return 200 so provider won't retry (test endpoint)
    try:
        await order.save(update_fields=["metadata"])
    except Exception:
        await order.save()
    return {"success": False, "message": "Payment not successful according to webhook payload", "status": tx_status, "payload": payload}




@router.get("/test/pay-last")
@router.post("/test/pay-last")
async def pay_last_order_no_auth(request: Request):
    """Test endpoint to mark the most recent unpaid order(s) as paid"""
    
    # Parse query params to allow targeting specific orders
    params = dict(request.query_params)
    search_order_id = params.get("order_id")
    search_cf_link_id = params.get("cf_link_id") or params.get("link_id")
    
    # Try to parse body for POST requests
    body = None
    if request.method == "POST":
        try:
            body = await request.json()
            if body:
                search_order_id = search_order_id or body.get("order_id")
                search_cf_link_id = search_cf_link_id or body.get("cf_link_id")
        except Exception:
            pass
    
    # Find the order
    order = None
    
    # If specific order_id provided, try to find it
    if search_order_id:
        order = await Order.filter(
            id=search_order_id,
            payment_status="unpaid"
        ).prefetch_related('user', 'items__item__vendor', 'sub_orders__vendor').first()
    
    # If cf_link_id provided, search in metadata
    if not order and search_cf_link_id:
        recent_orders = await Order.filter(
            payment_status="unpaid"
        ).order_by('-created_at').prefetch_related(
            'user', 'items__item__vendor', 'sub_orders__vendor'
        ).limit(50)
        
        for o in recent_orders:
            if o.metadata and "cashfree" in o.metadata:
                cf = o.metadata["cashfree"]
                if str(cf.get("cf_link_id", "")).lower() == str(search_cf_link_id).lower():
                    order = o
                    break
    
    # If no order found yet, get the most recent unpaid order
    if not order:
        order = await Order.filter(
            payment_status="unpaid"
        ).order_by('-created_at').prefetch_related(
            'user', 'items__item__vendor', 'sub_orders__vendor'
        ).first()
    
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
            cf_payment_id = cashfree_data.get("cf_payment_id") or cashfree_data.get("cf_link_id")
            combined_order_ids = cashfree_data["combined_order_ids"]
            
            # Fetch all orders in the combined payment
            orders_to_process = await Order.filter(
                id__in=combined_order_ids
            ).prefetch_related('user', 'items__item__vendor', 'sub_orders__vendor')
            
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
        
        await ord.save(update_fields=["status", "payment_status", "metadata"])
        
        total_amount += ord.total
        
        print(f"[NO-AUTH LAST] ✅ Order {ord.id}: {old_status} → PROCESSING")
        
        # Send notifications to vendors (matching create_order logic)
        try:
            # Ensure sub_orders are loaded
            if not hasattr(ord, 'sub_orders'):
                await ord.fetch_related('sub_orders__vendor')
            
            for sub_order in ord.sub_orders:
                # Send WebSocket notification to vendor
                payload = {
                    "type": "order_placed",
                    "order_id": ord.id,
                    "sub_order_id": sub_order.id,
                    "tracking_number": sub_order.tracking_number,
                    "customer_name": ord.user.name if ord.user else "Customer",
                    "payment_method": "Online Payment"
                }
                
                await manager.send_to(
                    payload, 
                    "vendors", 
                    str(sub_order.vendor_id), 
                    "notifications"
                )
                
                # Send push notification to vendor
                await send_notification(
                    sub_order.vendor_id,
                    "New Order - Payment Confirmed",
                    f"New paid order received: {sub_order.tracking_number}"
                )
        except Exception as e:
            print(f"[NO-AUTH LAST] Vendor notification error for order {ord.id}: {e}")
        
        # Send notification to customer
        try:
            if ord.user:
                await send_notification(
                    ord.user.id,
                    "Payment Successful",
                    f"Your payment for order #{ord.id} has been confirmed."
                )
        except Exception as e:
            print(f"[NO-AUTH LAST] Customer notification error for order {ord.id}: {e}")
        
        processed_orders.append({
            "order_id": ord.id,
            "old_status": old_status,
            "new_status": "processing",
            "total": float(ord.total),
            "sub_orders_count": len(ord.sub_orders) if hasattr(ord, 'sub_orders') else 0,
            "tracking_numbers": [so.tracking_number for so in ord.sub_orders] if hasattr(ord, 'sub_orders') else []
        })
    
    # Prepare response
    response = {
        "success": True,
        "message": f"✅ {'Combined payment' if is_combined else 'Order'} marked as paid!",
        "orders_count": len(processed_orders),
        "total_amount": float(total_amount),
        "processed_orders": processed_orders,
        "customer_name": order.user.name if order.user else "Unknown",
        "payment_status": "paid",
        "is_combined_payment": is_combined,
        "note": "⚠️ This is a TEST payment endpoint - Remove in production!"
    }
    
    if is_combined and cf_payment_id:
        response["cf_payment_id"] = cf_payment_id
    
    return response