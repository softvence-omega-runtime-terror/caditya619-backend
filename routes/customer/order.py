import httpx
from applications.customer.services import OrderService
from fastapi import APIRouter, HTTPException, Query, Request, status, Depends, Form
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
import uuid
from applications.user.models import User
from applications.customer.models import Order, OrderItem, OrderStatus
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
async def place_order(
    order_data: OrderCreateSchema, 
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    STEP 1: Create orders (one per vendor) with PENDING status
    STEP 2: Return combined payment link if payment method is Cashfree
    STEP 3: Orders progress only after successful payment
    """
    
    service = OrderService()
    try:
        # Create orders (one per vendor)
        orders = await service.create_orders(order_data, current_user)
        
        payment_method = order_data.payment_method.type
        if hasattr(payment_method, 'value'):
            payment_method = payment_method.value
        payment_method = str(payment_method)
        
        requires_payment = payment_method.lower() == "cashfree"
        
        # Calculate total amount across all orders
        total_amount = sum(float(order.total) for order in orders)
        
        response_data = {
            "success": True,
            "message": f"{len(orders)} order(s) created successfully",
            "data": {
                "orders": [
                    {
                        "order_id": order.id,
                        "vendor_id": order.vendor_id,
                        "status": order.status.value if hasattr(order.status, 'value') else order.status,
                        "tracking_number": order.tracking_number,
                        "total": float(order.total)
                    }
                    for order in orders
                ],
                "total_amount": total_amount,
                "payment_status": "unpaid",
                "requires_payment": requires_payment
            }
        }
        
        if requires_payment:
            # Generate combined payment link for all orders
            try:
                payment_link_response = await create_payment_link_for_orders(orders)
                response_data["data"]["payment_link"] = payment_link_response["payment_link"]
                response_data["data"]["cf_payment_id"] = payment_link_response["cf_payment_id"]
                response_data["message"] = f"{len(orders)} order(s) created. Please complete payment to proceed."
            except Exception as e:
                print(f"Payment link creation error: {e}")
                response_data["message"] = f"{len(orders)} order(s) created but payment link generation failed."
        else:
            # COD orders - notify immediately
            for order in orders:
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
                    
                    # Notify vendor
                    vendor = await VendorProfile.get_or_none(id=order.vendor_id)
                    if vendor:
                        await manager.send_to(payload, "vendors", str(vendor.user_id), "notifications")
                        await send_notification(
                            vendor.user_id, 
                            "New COD Order", 
                            f"New order #{order.id} received"
                        )
                except Exception as e:
                    print(f"Notification error for order {order.id}: {e}")
        
        return response_data
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")
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
    if current_user.is_superuser:
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
        'rider__user',
        'vendor__vendor_profile'
    )
    
    # Build response
    results = []
    for order in orders:
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
                "rider_id": order.rider.user_id,
                "rider_name": order.rider.user.name,
                "rider_phone": order.rider.user.phone,
                "rider_image": order.rider.profile_image
            }
            print(f"RIDER INFO FOR ORDER {order.rider.user_id}")
        
        # Payment link
        payment_link = None
        if order.payment_status == "unpaid" and order.metadata:
            cashfree_data = order.metadata.get("cashfree", {})
            payment_link = cashfree_data.get("payment_link")
        
        # Get vendor info (preserved even if vendor deleted)
        vendor_info = None
        if order.metadata and "vendor_info" in order.metadata:
            vendor_info = order.metadata["vendor_info"]
        elif order.vendor:
            # Fallback to live vendor data if metadata not available
            vendor_profile = await VendorProfile.get_or_none(user=order.vendor)
            vendor_info = {
                "vendor_id": order.vendor_id,
                "vendor_name": order.vendor.name,
                "vendor_phone": order.vendor.phone,
                "vendor_email": order.vendor.email or None,
                "is_vendor": order.vendor.is_vendor,
                "is_active": order.vendor.is_active
            }
            
            if vendor_profile:
                vendor_info.update({
                    "store_name": vendor_profile.owner_name,
                    "store_type": vendor_profile.type,
                    "store_latitude": vendor_profile.latitude,
                    "store_longitude": vendor_profile.longitude,
                    "kyc_status": vendor_profile.kyc_status,
                    "profile_is_active": vendor_profile.is_active
                })
        
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
            "rider_info": rider_info,
            "vendor_info": vendor_info
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
        'rider__user',
        'vendor__vendor_profile'
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check authorization
    if order.user_id != current_user.id and not current_user.is_staff:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    
    # # Get vendors locations
    # vendors_locations = await order.get_all_vendors_locations()
    
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
    # NEW: Get vendor info (preserved even if vendor deleted)
    vendor_info = None
    if order.metadata and "vendor_info" in order.metadata:
        vendor_info = order.metadata["vendor_info"]
    elif order.vendor:
        # Fallback to live vendor data if metadata not available
        vendor_profile = await VendorProfile.get_or_none(user=order.vendor)
        vendor_info = {
            "vendor_id": order.vendor_id,
            "vendor_name": order.vendor.name,
            "vendor_phone": order.vendor.phone,
            "vendor_email": order.vendor.email or None,
            "is_vendor": order.vendor.is_vendor,
            "is_active": order.vendor.is_active
        }
        
        if vendor_profile:
            vendor_info.update({
                "store_name": vendor_profile.owner_name,
                "store_type": vendor_profile.type,
                "store_latitude": vendor_profile.latitude,
                "store_longitude": vendor_profile.longitude,
                "kyc_status": vendor_profile.kyc_status,
                "profile_is_active": vendor_profile.is_active
            })
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
        # "vendors": vendors_locations,
        "rider_info": rider_info,
        "vendor_info": vendor_info,
        "can_cancel": order_status.lower() == "pending"
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
    - Only the customer who created the order can update it
    - Only pending orders can be cancelled
    - Can only update status to "cancelled"
    """
    
    order = await Order.get_or_none(id=order_id).prefetch_related('user')
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Only order owner can update
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=403, 
            detail="Not authorized to update this order"
        )
    
    # Get current status
    current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    
    # Only pending orders can be updated
    if current_status.lower() != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update order with status: {current_status}. Only pending orders can be cancelled."
        )
    
    # Only "cancelled" status is allowed
    if not update_data.status:
        raise HTTPException(status_code=400, detail="Status is required")
    
    if update_data.status.lower() != "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Can only update status to 'cancelled'"
        )
    
    # Update status
    try:
        new_status = OrderStatus.CANCELLED
        order.status = new_status
        
        # Add cancellation reason if provided
        if update_data.reason:
            order.reason = update_data.reason
            await order.save(update_fields=['status', 'reason', 'updated_at'])
        else:
            await order.save(update_fields=['status', 'updated_at'])
        
        print(f"[UPDATE] Order {order_id} status: {current_status} → cancelled")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating order: {str(e)}")
    
    # Send notification
    try:
        await send_notification(
            order.user_id,
            "Order Cancelled",
            f"Your order #{order_id} has been cancelled"
        )
    except Exception as e:
        print(f"[UPDATE] Notification error: {e}")
    
    return {
        "success": True,
        "message": "Order cancelled successfully",
        "order_id": order_id
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

async def create_payment_link_for_orders(orders: List[Order]):
    """
    Create a single payment link for multiple orders.
    All orders must belong to the same customer and use Cashfree payment method.
    """
    
    if not orders:
        raise HTTPException(status_code=400, detail="No orders provided")
    
    # Validate all orders
    customer_id = orders[0].user_id
    customer = orders[0].user
    total_amount = Decimal("0")
    order_ids = []
    
    for order in orders:
        # Check customer consistency
        if order.user_id != customer_id:
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
        
        total_amount += order.total
        order_ids.append(order.id)
    
    # Create combined payment link
    headers = {
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID.strip(),
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET.strip(),
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json"
    }
    
    # Generate unique payment ID
    cf_payment_id = f"PAY_{uuid.uuid4().hex[:12].upper()}"
    
    # Build payment purpose
    order_list = ", ".join(order_ids)
    payment_purpose = f"Payment for {len(orders)} orders: {order_list[:100]}"
    
    customer_name = customer.name or "Customer"
    customer_email = customer.email or f"customer_{customer.id}@example.com"
    customer_phone = customer.phone or "9999999999"
    
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
            "return_url": f"{settings.BACKEND_URL}/payment/payment/test/pay-last",  # ✅ Now handled
            "order_ids": ",".join(order_ids),
            "user_id": str(customer_id)
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
        
        # Update all orders with payment link info
        payment_info = {
            "cf_payment_id": cf_payment_id,
            "payment_link": payment_link,
            "link_status": data.get("link_status"),
            "created_at": data.get("link_created_at"),
            "is_combined_payment": True,
            "combined_order_ids": order_ids,
            "combined_total": float(total_amount)
        }
        
        for order in orders:
            if order.metadata is None:
                order.metadata = {}
            
            order.metadata["cashfree"] = payment_info.copy()
            order.cf_order_id = cf_payment_id
            
            await order.save(update_fields=["metadata", "cf_order_id"])
        
        print(f"[PAYMENT] ✅ Payment link created: {payment_link}")
        
        return {
            "success": True,
            "cf_payment_id": cf_payment_id,
            "payment_link": payment_link,
            "total_amount": float(total_amount),
            "orders_count": len(orders)
        }
        
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





#*****************************************
#    Rider Ratings
#*****************************************

@router.post("/rider/ratings/{order_id}")
async def create_rider_rating(
        order_id : str,
        rating : int = Form(None),
        comment : str = Form(None),    
        current_user: User = Depends(get_current_user)
    ):
    order = await Order.get(id=order_id)
    if not order or order.status != OrderStatus.DELIVERED or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    rider = await RiderProfile.get(id=order.rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    rider_review = await RiderReview.create(
        rating=rating,
        comment=comment,
        user=current_user,
        rider=rider
    )
    await rider_review.save()
    
    return {
        "success": True,
        "message": "Rider Rating Created Successfully",
        "retings": {
            "id": rider_review.id,
            "rating": rider_review.rating,
            "comment": rider_review.comment,
            "user": rider_review.user.name,
            "created_at": rider_review.created_at.isoformat(),
        }
    }




@router.post("/complaints/{order_id}")
async def create_complaint(
        order_id : str,
        description : str = Form(...),
        is_serious : bool = Form(False),
        current_user: User = Depends(get_current_user)
    ):
    order = await Order.get(id=order_id)
    if not order or order.status != OrderStatus.DELIVERED or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    rider = await RiderProfile.get(id=order.rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    complaint = await Complaint.create(
        rider = rider,
        user = current_user,
        description=description,
        is_serious=is_serious
    )
    await complaint.save()

    return {
        "success": True,
        "message": "Complaint Created Successfully",
        "complaint": {
            "id": complaint.id,
            "description": complaint.description,
            "is_serious": complaint.is_serious,
            "user": complaint.user.name,
            "created_at": complaint.created_at.isoformat(),
        }
    }