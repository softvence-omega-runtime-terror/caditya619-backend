import httpx
from applications.customer.services import OrderService
from fastapi import APIRouter, HTTPException, Query, Request, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
import uuid
from applications.user import vendor
from applications.user.models import *
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from app.token import get_current_user
from app.config import settings
from applications.user.rider import RiderProfile
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
async def place_order(
    order_data: OrderCreateSchema, 
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    STEP 1: Create order with PENDING status
    STEP 2: Return payment link if payment method is Cashfree
    STEP 3: Order progresses only after successful payment
    """
    
    service = OrderService()
    try:
        # Create order with PENDING status
        order = await service.create_order(order_data, current_user)
        
        payment_method = order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
        requires_payment = payment_method.lower() == "cashfree"
        
        response_data = {
            "success": True,
            "message": "Order created successfully",
            "data": {
                "order_id": order.id,
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "tracking_number": order.tracking_number,
                "total": float(order.total),
                "payment_status": order.payment_status,
                "requires_payment": requires_payment
            }
        }
        
        if requires_payment:
            # Generate payment link using Cashfree
            try:
                payment_link_response = await create_payment_link_internal(order)
                response_data["data"]["payment_link"] = payment_link_response["payment_link"]
                response_data["data"]["cf_order_id"] = payment_link_response["cf_order_id"]
                response_data["message"] = "Order created. Please complete payment to proceed."
            except Exception as e:
                print(f"Payment link creation error: {e}")
                response_data["message"] = "Order created but payment link generation failed. Please try manual payment."
        else:
            # COD order - notify immediately
            payload = {
                "type": "order_placed",
                "order_id": order.id,
                "customer_name": current_user.name,
                "payment_method": "COD",
                "created_at": datetime.utcnow().isoformat()
            }
            
            try:
                await redis.publish("order_updates", json.dumps(payload))
                await manager.send_to(payload, "customers", str(current_user.id), "notifications")
                
                # Notify all vendors
                order_items = await OrderItem.filter(order=order).prefetch_related('item__vendor')
                vendor_ids = set()
                for oi in order_items:
                    vendor_ids.add(oi.item.vendor_id)
                
                for vendor_id in vendor_ids:
                    vendor = await VendorProfile.get_or_none(id=vendor_id)
                    if vendor:
                        await manager.send_to(payload, "vendors", str(vendor.user_id), "notifications")
                        await send_notification(
                            vendor.user_id, 
                            "New COD Order", 
                            f"New order #{order.id} received"
                        )
            except Exception as e:
                print(f"Notification error: {e}")
        
        return response_data
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")


# ============================================================
# COMPLETE ORDER CRUD - applications.customer.routes.py
# ============================================================

# from fastapi import APIRouter, HTTPException, Depends, Query, status
# from typing import Optional, List
# from datetime import datetime

# router = APIRouter(prefix='/orders', tags=['Orders'])

# # ============================================================
# # 1. CREATE ORDER (Already Implemented)
# # ============================================================

# @router.post("/", status_code=status.HTTP_201_CREATED)
# async def place_order(
#     order_data: OrderCreateSchema, 
#     current_user: User = Depends(get_current_user),
#     redis = Depends(get_redis)
# ):
#     """Create new order with payment link if needed"""
#     # Implementation already provided in previous artifacts
#     pass


# ============================================================
# 2. GET ALL ORDERS (with filters and pagination)
# ============================================================

@router.get("/")  # ✅ NO response_model here!
async def get_all_orders(
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, processing, confirmed, etc."),
    payment_status: Optional[str] = Query(None, description="Filter by payment status: unpaid, paid, failed"),
    limit: int = Query(10, ge=1, le=100, description="Number of orders to return"),
    offset: int = Query(0, ge=0, description="Number of orders to skip"),
    sort_by: str = Query("created_at", description="Sort field: created_at, total, status"),
    sort_order: str = Query("desc", description="Sort order: asc or desc")
):
    """
    Get all orders for current user with filters and pagination.
    Admins can see all orders, regular users see only their own.
    """
    
    # Build query
    if current_user.is_staff:
        query = Order.all()
    else:
        query = Order.filter(user_id=current_user.id)
    
    # Apply status filter
    if status_filter:
        try:
            status_enum = OrderStatus[status_filter.upper()]
            query = query.filter(status=status_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    
    # Apply payment status filter
    if payment_status:
        query = query.filter(payment_status=payment_status.lower())
    
    # Apply sorting
    sort_field = sort_by if sort_by in ['created_at', 'total', 'order_date'] else 'created_at'
    if sort_order.lower() == 'desc':
        query = query.order_by(f'-{sort_field}')
    else:
        query = query.order_by(sort_field)
    
    # Get total count
    total_count = await query.count()
    
    # Apply pagination
    orders = await query.offset(offset).limit(limit).prefetch_related(
        'user',
        'items__item',
        'rider__user'
    )
    
    # Build response
    results = []
    for order in orders:
        # Get vendors locations
        vendors_locations = await order.get_all_vendors_locations()
        
        # Get shipping address from metadata
        shipping_address = None
        if order.metadata and "shipping_address" in order.metadata:
            shipping_address = order.metadata["shipping_address"]
        
        # Get delivery and payment info
        delivery_option = order.metadata.get("delivery_option", {}) if order.metadata else {
            "type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else str(order.delivery_type),
            "price": float(order.delivery_fee)
        }
        
        payment_method = order.metadata.get("payment_method", {}) if order.metadata else {
            "type": order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
        }
        
        # Build items list
        items = []
        for order_item in order.items:
            items.append({
                "item_id": order_item.item_id,
                "title": order_item.title,
                "price": order_item.price,
                "quantity": order_item.quantity,
                "image_path": order_item.image_path
            })
        
        # Rider info (only if OUT_FOR_DELIVERY)
        rider_info = None
        order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        if order_status.lower() == "outfordelivery" and order.rider:
            rider_info = {
                "rider_id": order.rider.id,
                "rider_name": order.rider.user.name,
                "rider_phone": order.rider.user.phone,
                "rider_image": order.rider.profile_image
            }
        
        # Payment link
        payment_link = None
        if order.payment_status == "unpaid" and order.metadata:
            cashfree_data = order.metadata.get("cashfree", {})
            payment_link = cashfree_data.get("payment_link")
        
        results.append({
            "id": order.id,
            "user_id": str(order.user_id),
            "items": items,
            "shipping_address": shipping_address,
            "delivery_option": delivery_option,
            "payment_method": payment_method,
            "subtotal": float(order.subtotal),
            "delivery_fee": float(order.delivery_fee),
            "total": float(order.total),
            "coupon_code": order.coupon_code,
            "discount": float(order.discount),
            "order_date": order.order_date.isoformat(),
            "status": order_status,
            "transaction_id": order.transaction_id,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery.isoformat() if order.estimated_delivery else None,
            "payment_status": order.payment_status,
            "payment_link": payment_link,
            "vendors": vendors_locations,
            "rider_info": rider_info
        })
    
    # Return with pagination metadata
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "orders": results
    }


# ============================================================
# 3. GET SINGLE ORDER
# ============================================================

@router.get("/{order_id}")
async def get_order_details(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed information about a specific order"""
    
    order = await Order.get_or_none(id=order_id).prefetch_related(
        'user',
        'items__item',
        'rider__user'
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check authorization
    if order.user_id != current_user.id and not current_user.is_staff:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    
    # Get vendors locations
    vendors_locations = await order.get_all_vendors_locations()
    
    # Get shipping address from metadata
    shipping_address = None
    if order.metadata and "shipping_address" in order.metadata:
        shipping_address = order.metadata["shipping_address"]
    
    # Get delivery and payment info
    delivery_option = order.metadata.get("delivery_option", {}) if order.metadata else {
        "type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else str(order.delivery_type),
        "price": float(order.delivery_fee)
    }
    
    payment_method = order.metadata.get("payment_method", {}) if order.metadata else {
        "type": order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)
    }
    
    # Build items list
    items = []
    for order_item in order.items:
        items.append({
            "item_id": order_item.item_id,
            "title": order_item.title,
            "price": order_item.price,
            "quantity": order_item.quantity,
            "image_path": order_item.image_path
        })
    
    # Rider info (only if OUT_FOR_DELIVERY)
    rider_info = None
    order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    if order_status.lower() == "outfordelivery" and order.rider:
        rider_info = {
            "rider_id": order.rider.id,
            "rider_name": order.rider.user.name,
            "rider_phone": order.rider.user.phone,
            "rider_image": order.rider.profile_image
        }
    
    # Payment link
    payment_link = None
    if order.payment_status == "unpaid" and order.metadata:
        cashfree_data = order.metadata.get("cashfree", {})
        payment_link = cashfree_data.get("payment_link")
    
    return {
        "order_id": order.id,
        "user_id": str(order.user_id),
        "items": items,
        "shipping_address": shipping_address,
        "delivery_option": delivery_option,
        "payment_method": payment_method,
        "subtotal": float(order.subtotal),
        "delivery_fee": float(order.delivery_fee),
        "total": float(order.total),
        "coupon_code": order.coupon_code,
        "discount": float(order.discount),
        "order_date": order.order_date.isoformat(),
        "status": order_status,
        "transaction_id": order.transaction_id,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery.isoformat() if order.estimated_delivery else None,
        "payment_status": order.payment_status,
        "payment_link": payment_link,
        "vendors": vendors_locations,
        "rider_info": rider_info
    }


# ============================================================
# 4. UPDATE ORDER
# ============================================================

class OrderUpdateSchema(BaseModel):
    status: Optional[str] = None
    rider_id: Optional[int] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
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
        if current_status.lower() not in ["pending", "processing"]:
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
            order.status = new_status
            updated_fields.append('status')
            
            # If cancelling, add reason
            if update_data.status.lower() == "cancelled" and update_data.reason:
                order.reason = update_data.reason
                updated_fields.append('reason')
            
            print(f"[UPDATE] Order {order_id} status: {old_status} → {update_data.status}")
            
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_data.status}")
    
    if update_data.rider_id is not None:
        # Verify rider exists
        rider = await RiderProfile.get_or_none(id=update_data.rider_id)
        if not rider:
            raise HTTPException(status_code=404, detail="Rider not found")
        
        order.rider_id = update_data.rider_id
        updated_fields.append('rider_id')
        print(f"[UPDATE] Order {order_id} assigned to rider {update_data.rider_id}")
    
    if update_data.tracking_number:
        order.tracking_number = update_data.tracking_number
        updated_fields.append('tracking_number')
    
    if update_data.estimated_delivery:
        order.estimated_delivery = update_data.estimated_delivery
        updated_fields.append('estimated_delivery')
    
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
            if update_data.rider_id and update_data.status and update_data.status.lower() == "outfordelivery":
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
            "updated_fields": updated_fields
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
    
    if current_status.lower() in ["delivered", "cancelled"]:
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

async def create_payment_link_internal(order: Order):
    """Internal function to create payment link"""
    
    customer_name = order.metadata.get("shipping_address", {}).get("full_name", "Customer")
    customer_phone = order.metadata.get("shipping_address", {}).get("phone_number", order.user.phone)
    customer_email = order.user.email or f"customer_{order.user.id}@example.com"
    
    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json"
    }
    
    cf_order_id = f"CF_{order.id}_{uuid.uuid4().hex[:8].upper()}"
    
    payload = {
        "link_id": cf_order_id,
        "link_amount": float(order.total),
        "link_currency": "INR",
        "link_purpose": f"Payment for order {order.id}",
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
            "order_id": order.id,
            "user_id": str(order.user.id),
            "return_url": f"{settings.BACKEND_URL}/payment/payment/webhook/test"
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{CASHFREE_BASE}/links",
            json=payload,
            headers=headers
        )
    
    data = resp.json()
    
    if resp.status_code not in [200, 201]:
        raise Exception(f"Cashfree API error: {data.get('message', 'Unknown error')}")
    
    payment_link = data.get("link_url")
    
    # Save payment link to order metadata
    if order.metadata is None:
        order.metadata = {}
    
    order.metadata["cashfree"] = {
        "cf_link_id": cf_order_id,
        "payment_link": payment_link,
        "link_status": data.get("link_status"),
        "created_at": data.get("link_created_at")
    }
    
    await order.save(update_fields=["metadata"])
    
    return {
        "cf_order_id": cf_order_id,
        "payment_link": payment_link
    }

