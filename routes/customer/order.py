import httpx
from applications.customer.services import OrderService
from fastapi import APIRouter, HTTPException, Query, Request, status, Depends, Form, Response
from fastapi.responses import RedirectResponse
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
import uuid
from applications.user.models import *
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from app.token import get_current_user
from app.config import settings
from applications.user.rider import RiderReview, RiderProfile, Complaint
from routes.payment.payment import CASHFREE_API_VERSION, CASHFREE_BASE, CASHFREE_CLIENT_PAYMENT_ID, CASHFREE_CLIENT_PAYMENT_SECRET
from routes.rider.notifications import send_notification
from app.redis import get_redis
import json
from applications.user.vendor import VendorProfile
from app.utils.websocket_manager import manager

router = APIRouter(prefix="/orders", tags=["Orders"])



# ============================================================
# ROUTER - applications.customer.routes.py
# ============================================================

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreateSchema,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    Create order with automatic sub-order creation per vendor
    """
    service = OrderService()
    
    try:
        # Create parent order with sub-orders
        order = await service.create_order_with_sub_orders(order_data, current_user)
        
        # Ensure tracking numbers are unique per vendor (not based on items)
        try:
            vendor_counts = {}
            for sub_order in order.sub_orders:
                # vendor_id may be an attribute or a relation
                vid = getattr(sub_order, "vendor_id", None) or (getattr(sub_order, "vendor", None) and getattr(sub_order.vendor, "id", None))
                if vid is None:
                    # skip if vendor id can't be determined
                    continue
                vendor_counts[vid] = vendor_counts.get(vid, 0) + 1
                new_tracking = f"{vid}-{str(order.id)[:8].upper()}-{vendor_counts[vid]}"
                # update only if different to avoid unnecessary writes
                if getattr(sub_order, "tracking_number", None) != new_tracking:
                    sub_order.tracking_number = new_tracking
                    try:
                        await sub_order.save(update_fields=["tracking_number"])
                    except Exception as e:
                        print(f"[TRACKING] Failed to save tracking for sub_order {getattr(sub_order,'id', None)}: {e}")
        except Exception as e:
            print(f"[TRACKING] Error ensuring per-vendor tracking numbers: {e}")
        
        # Determine payment method (with fallback to metadata)
        try:
            payment_method = ""
            if hasattr(order, 'payment_method') and order.payment_method is not None:
                payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
            elif getattr(order, "metadata", None):
                # fallback if payment method stored in metadata
                payment_method = str(order.metadata.get("payment_method", ""))
            payment_method = (payment_method or "").strip()
        except Exception:
            payment_method = ""
        
        requires_payment = payment_method.lower() in ["cashfree", "online", "upi"]
        # Only require payment if order total > 0
        requires_payment = requires_payment and (float(order.total) > 0)
        
        response_data = {
            "success": True,
            "message": "Order created successfully",
            "data": {
                "order_id": order.id,
                "sub_orders_count": len(order.sub_orders),
                "tracking_numbers": [so.tracking_number for so in order.sub_orders],
                "total": float(order.total),
                "payment_status": order.payment_status,
                "requires_payment": requires_payment
            }
        }
        
        if requires_payment:
            # Ensure cashfree credentials are present
            if not (CASHFREE_CLIENT_PAYMENT_ID and CASHFREE_CLIENT_PAYMENT_SECRET and CASHFREE_BASE):
                response_data["message"] = "Order created but payment configuration is missing."
            else:
                try:
                    # Create payment link for entire order
                    payment_link_response = await create_payment_link_for_order(order)
                    if payment_link_response:
                        response_data["data"]["payment_link"] = payment_link_response.get("payment_link", "")
                        response_data["data"]["cf_order_id"] = payment_link_response.get("cf_order_id", "")
                        response_data["message"] = "Order created. Please complete payment to proceed."
                    else:
                        response_data["message"] = "Order created but payment link generation returned no data."
                except Exception as e:
                    print(f"Payment link error: {e}")
                    response_data["message"] = "Order created but payment link generation failed."
        else:
            # COD order - notify vendors
            try:
                for sub_order in order.sub_orders:
                    payload = {
                        "type": "order_placed",
                        "order_id": order.id,
                        "sub_order_id": sub_order.id,
                        "tracking_number": sub_order.tracking_number,
                        "customer_name": current_user.name,
                        "payment_method": "COD"
                    }
                    
                    await manager.send_to(payload, "vendors", str(sub_order.vendor_id), "notifications")
                    await send_notification(
                        sub_order.vendor_id,
                        "New Order",
                        f"New order received: {sub_order.tracking_number}"
                    )
            except Exception as e:
                print(f"Notification error: {e}")
        
        return response_data
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET ORDER WITH SUB-ORDERS (Your Required Format)
# ============================================================

@router.get("/{order_id}")
async def get_order_details(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get order with sub-orders in the specified format
    """
    
    order = await Order.get_or_none(id=order_id).prefetch_related(
        'user',
        'sub_orders__items__item',
        'sub_orders__vendor__vendor_profile',
        'sub_orders__rider__user'
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check authorization
    if order.user_id != current_user.id and not current_user.is_staff:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Build sub-orders array
    sub_orders_data = []
    
    for sub_order in order.sub_orders:
        # Build items array
        items = []
        for item in sub_order.items:
            items.append({
                "item_id": item.item_id,
                "title": item.title,
                "price": item.price,
                "quantity": item.quantity,
                "image_path": item.image_path
            })
        
        # Vendor info (from stored JSON)
        vendor_info = sub_order.vendor_info
        
        # Rider info (only if assigned and status is OUT_FOR_DELIVERY)
        rider_info = None
        sub_order_status = sub_order.status.value if hasattr(sub_order.status, 'value') else str(sub_order.status)
        
        if sub_order_status.lower() == "outfordelivery" and sub_order.rider:
            rider_info = {
                "rider_id": sub_order.rider.id,
                "name": sub_order.rider.user.name,
                "phone": sub_order.rider.user.phone,
                "vehicle": getattr(sub_order.rider, 'vehicle_type', 'Bike'),
                "vehicle_number": getattr(sub_order.rider, 'vehicle_number', 'N/A')
            }
        
        # Delivery option
        delivery_option = sub_order.delivery_option or {}
        
        # Payment method (from parent order)
        payment_method_data = order.metadata.get("payment_method", {}) if order.metadata else {}
        
        sub_orders_data.append({
            "tracking_number": sub_order.tracking_number,
            "items": items,
            "vendor_info": vendor_info,
            "rider_info": rider_info,
            "delivery_option": delivery_option,
            "payment_method": payment_method_data,
            "status": sub_order_status,
            "estimated_delivery": sub_order.estimated_delivery.strftime("%Y-%m-%d %H:%M") if sub_order.estimated_delivery else None
        })
    
    # Get payment link if exists
    payment_link = ""
    if order.metadata and "cashfree" in order.metadata:
        payment_link = order.metadata["cashfree"].get("payment_link", "")
    
    # Build final response
    response = {
        "order_id": order.id,
        "user_id": str(order.user_id),
        "sub_orders": sub_orders_data,  # This is now an array!
        "shipping_address": order.shipping_address,
        "subtotal": float(order.subtotal),
        "delivery_fee": float(order.delivery_fee),
        "total": float(order.total),
        "coupon_code": order.coupon_code or "",
        "discount": float(order.discount),
        "order_date": order.order_date.strftime("%Y-%m-%d %H:%M"),
        "transaction_id": order.transaction_id or "",
        "payment_status": order.payment_status,
        "payment_link": payment_link,
        "can_cancel": order.can_cancel
    }
    
    return response


# ============================================================
# GET ALL ORDERS WITH SUB-ORDERS
# ============================================================

@router.get("/")
async def get_all_orders(
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    """
    Get all orders with sub-orders summary
    """
    
    query = Order.filter(user_id=current_user.id) if not current_user.is_staff else Order.all()
    
    total = await query.count()
    orders = await query.offset(offset).limit(limit).prefetch_related(
        'sub_orders__vendor',
        'sub_orders__items'
    ).order_by('-created_at')
    
    results = []
    for order in orders:
        # Count sub-orders by status
        sub_order_statuses = {}
        for sub_order in order.sub_orders:
            status = sub_order.status.value if hasattr(sub_order.status, 'value') else str(sub_order.status)
            sub_order_statuses[status] = sub_order_statuses.get(status, 0) + 1
        
        results.append({
            "order_id": order.id,
            "sub_orders_count": len(order.sub_orders),
            "sub_order_statuses": sub_order_statuses,
            "total": float(order.total),
            "payment_status": order.payment_status,
            "order_date": order.order_date.isoformat(),
            "can_cancel": order.can_cancel
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "orders": results
    }







# ============================================================
# 4. UPDATE ORDER
# ============================================================

class OrderUpdateSchema(BaseModel):
    status: Optional[str] = None
    # rider_id: Optional[int] = None
    # tracking_number: Optional[str] = None
    # estimated_delivery: Optional[datetime] = None
    reason: Optional[str] = None  # For cancellation reason
    
    class Config:
        from_attributes = True


@router.patch("/{order_id}")
async def update_order(
    order_id: str,
    update_data: OrderUpdateSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Update order details.
    - Customers can only cancel their pending orders
    - Staff/Vendors can update status, assign riders, etc.
    """
    
    order = await Order.get_or_none(id=order_id).prefetch_related('user')
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Authorization check
    is_owner = order.user_id == current_user.id
    is_authorized = current_user.is_staff or current_user.is_vendor
    
    if not (is_owner or is_authorized):
        raise HTTPException(status_code=403, detail="Not authorized to update this order")
    
    # Customers can only cancel pending orders
    if is_owner and not is_authorized:
        if update_data.status and update_data.status.lower() != "cancelled":
            raise HTTPException(
                status_code=403,
                detail="Customers can only cancel orders"
            )
        
        current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        if current_status.lower() not in ["pending"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel order with status: {current_status}"
            )
    
    # Update fields
    updated_fields = []
    
    if update_data.status:
        try:
            new_status = OrderStatus[update_data.status.upper()]
            old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
            if new_status != "cancelled":
                raise HTTPException(status_code=400, detail="Only cancellation allowed")
            else:
                # Only staff can change status to cancelled
                order.status = new_status
                updated_fields.append('status')
            
                # If cancelling, add reason
                if update_data.status.lower() == "cancelled" and update_data.reason:
                    order.reason = update_data.reason
                    updated_fields.append('reason')
                
                print(f"[UPDATE] Order {order_id} status: {old_status} → {update_data.status}")
                
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_data.status}")
    
    # if update_data.rider_id is not None:
    #     # Verify rider exists
    #     rider = await RiderProfile.get_or_none(id=update_data.rider_id)
    #     if not rider:
    #         raise HTTPException(status_code=404, detail="Rider not found")
        
    #     order.rider_id = update_data.rider_id
    #     updated_fields.append('rider_id')
    #     print(f"[UPDATE] Order {order_id} assigned to rider {update_data.rider_id}")
    
    # if update_data.tracking_number:
    #     order.tracking_number = update_data.tracking_number
    #     updated_fields.append('tracking_number')
    
    # if update_data.estimated_delivery:
    #     order.estimated_delivery = update_data.estimated_delivery
    #     updated_fields.append('estimated_delivery')
    
    if updated_fields:
        order.updated_at = datetime.utcnow()
        updated_fields.append('updated_at')
        await order.save(update_fields=updated_fields)
        
        # Send notifications
        try:
            status_msg = update_data.status or "updated"
            
            # Notify customer
            await send_notification(
                order.user_id,
                "Order Updated",
                f"Your order #{order_id} status has been updated to {status_msg}"
            )
            
            # If rider assigned and status is OUT_FOR_DELIVERY
            if update_data.status and update_data.status.lower() == "outfordelivery":
                await send_notification(
                    order.user_id,
                    "Order Out for Delivery",
                    f"Your order #{order_id} is out for delivery!"
                )
        except Exception as e:
            print(f"[UPDATE] Notification error: {e}")
        
        return {
            "success": True,
            "message": "Order updated successfully",
            "order_id": order_id,
            # "updated_fields": updated_fields
        }
    
    return {
        "success": False,
        "message": "No fields to update"
    }


# ============================================================
# 5. DELETE ORDER (Soft Delete - Cancel)
# ============================================================

@router.delete("/{order_id}")
async def cancel_order(
    order_id: str,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Cancel an order (soft delete).
    - Customers can cancel pending/processing orders
    - Staff can cancel any order
    - Cannot cancel delivered orders
    """
    
    order = await Order.get_or_none(id=order_id).prefetch_related('user', 'items__item')
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Authorization check
    is_owner = order.user_id == current_user.id
    if not (is_owner or current_user.is_staff):
        raise HTTPException(status_code=403, detail="Not authorized to cancel this order")
    
    # Check if order can be cancelled
    current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    
    if current_status.lower() != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status: {current_status}"
        )
    
    # For paid orders, check if refund is needed
    if order.payment_status == "paid":
        # Add refund logic here if needed
        if order.metadata is None:
            order.metadata = {}
        order.metadata["refund_requested"] = True
        order.metadata["refund_requested_at"] = datetime.utcnow().isoformat()
    
    # Update order status
    old_status = current_status
    order.status = OrderStatus.CANCELLED
    order.reason = reason or "Cancelled by customer"
    order.updated_at = datetime.utcnow()
    
    await order.save(update_fields=['status', 'reason', 'updated_at', 'metadata'])
    
    # Restore stock for items
    for order_item in order.items:
        item = order_item.item
        item.stock += order_item.quantity
        item.total_sale -= order_item.quantity
        await item.save(update_fields=['stock', 'total_sale'])
    
    print(f"[CANCEL] Order {order_id} cancelled. Status: {old_status} → CANCELLED")
    
    # Send notifications
    try:
        await send_notification(
            order.user_id,
            "Order Cancelled",
            f"Your order #{order_id} has been cancelled. Reason: {order.reason}"
        )
        
        # Notify vendors
        vendor_ids = set()
        for order_item in order.items:
            vendor_ids.add(order_item.item.vendor_id)
        
        for vendor_id in vendor_ids:
            vendor = await VendorProfile.get_or_none(id=vendor_id)
            if vendor:
                await send_notification(
                    vendor.user_id,
                    "Order Cancelled",
                    f"Order #{order_id} has been cancelled."
                )
    except Exception as e:
        print(f"[CANCEL] Notification error: {e}")
    
    return {
        "success": True,
        "message": "Order cancelled successfully",
        "order_id": order_id,
        "old_status": old_status,
        "new_status": "cancelled",
        "refund_requested": order.payment_status == "paid"
    }    


# ============================================================
# PAYMENT HELPER - Internal function
# ============================================================

async def create_payment_link_for_order(order: Order):
    # Ensure user relation loaded
    if not hasattr(order, "user") or order.user is None:
        await order.fetch_related("user")

    customer_name = (order.shipping_address or {}).get("full_name", "Customer")
    customer_phone = (order.shipping_address or {}).get("phone_number", getattr(order.user, "phone", ""))
    customer_email = getattr(order.user, "email", None) or f"customer_{getattr(order.user, 'id', 'unknown')}@example.com"

    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json",
    }

    cf_order_id = f"CF_{order.id}_{uuid.uuid4().hex[:8].upper()}"

    # Prepare a few possible payload shapes (Cashfree variants differ by account/type)
    payload_variants = [
        # variant A (link based)
        {
            "link_id": cf_order_id,
            "link_amount": float(order.total),
            "link_currency": "INR",
            "link_purpose": f"Payment for order {order.id}",
            "customer_details": {
                "customer_phone": customer_phone,
                "customer_email": customer_email,
                "customer_name": customer_name,
            },
            "link_notify": {"send_sms": True, "send_email": True},
            "link_meta": {
                "order_id": order.id,
                "user_id": str(getattr(order.user, "id", "")),
                "return_url": f"{settings.BACKEND_URL}/payment/test/webhook",
            },
        },
        # variant B (simple payment page)
        {
            "orderId": cf_order_id,
            "orderAmount": float(order.total),
            "orderCurrency": "INR",
            "orderNote": f"Payment for order {order.id}",
            "customerName": customer_name,
            "customerPhone": customer_phone,
            "customerEmail": customer_email,
            "notifyCustomer": True,
            "returnUrl": f"{settings.BACKEND_URL}/payment/test/webhook",
            "metadata": {"order_id": order.id, "user_id": str(getattr(order.user, "id", ""))},
        },
    ]

    base = (CASHFREE_BASE or "").rstrip("/")
    if not base:
        raise Exception("Cashfree base URL not configured")

    candidate_paths = [
        "links", "v1/links", "api/v1/links", "v2/links", "order/create", "orders", "payments/links"
    ]

    raw_results = []
    successful_data = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for path in candidate_paths:
            url = f"{base}/{path.lstrip('/')}"
            for payload in payload_variants:
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except Exception as e:
                    raw_results.append({"url": url, "error": str(e)})
                    continue

                entry = {"url": url, "status_code": resp.status_code}
                try:
                    entry["body"] = resp.json()
                except Exception:
                    entry["body_text"] = resp.text[:1000]
                raw_results.append(entry)

                if resp.status_code in (200, 201):
                    # try to extract link/id from multiple shapes
                    data = None
                    try:
                        data = resp.json()
                    except Exception:
                        data = entry.get("body_text") or {}
                    # multiple fallbacks for link url/id
                    payment_link = (
                        (data.get("link_url") if isinstance(data, dict) else None) or
                        (data.get("payment_link") if isinstance(data, dict) else None) or
                        (data.get("url") if isinstance(data, dict) else None) or
                        (data.get("data", {}).get("link_url") if isinstance(data, dict) else None) or
                        ""
                    )
                    link_id = (
                        (data.get("link_id") if isinstance(data, dict) else None) or
                        (data.get("id") if isinstance(data, dict) else None) or
                        (data.get("data", {}).get("link_id") if isinstance(data, dict) else None) or
                        cf_order_id
                    )
                    successful_data = {"cf_order_id": link_id, "payment_link": payment_link, "raw": data}
                    break
            if successful_data:
                break

    # persist raw results for debugging
    if order.metadata is None:
        order.metadata = {}
    order.metadata.setdefault("cashfree", {})
    order.metadata["cashfree"]["raw_attempts"] = raw_results
    order.metadata["cashfree"].setdefault("created_at", datetime.utcnow().isoformat())

    if not successful_data:
        # save metadata and raise clear error
        await order.save(update_fields=["metadata"])
        raise Exception("Failed to create Cashfree payment link; see order.metadata.cashfree.raw_attempts for details")

    # Save successful response into metadata and return concise info
    order.metadata["cashfree"].update({
        "cf_link_id": successful_data["cf_order_id"],
        "payment_link": successful_data["payment_link"],
        "last_success": successful_data["raw"],
    })
    await order.save(update_fields=["metadata"])

    return {"cf_order_id": successful_data["cf_order_id"], "payment_link": successful_data["payment_link"]}


# ============================================================
# WEBHOOK - Cashfree Test Webhook
# ============================================================



