import httpx
from applications.customer.services import OrderService
from fastapi import APIRouter, HTTPException, Query, status, Depends, Form
from typing import List, Optional
from datetime import datetime
import uuid
from applications.user.models import User
from applications.customer.models import Order, OrderStatus
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
from routes.payment.payment_helper import create_payment_session_for_orders

# Cashfree Configuration
CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"

router = APIRouter(prefix="/orders", tags=["Orders"])


# ============================================================
# ROUTER - applications.customer.routes.py
# ============================================================

# routes.customer.order.py

async def handle_phonepe_payment(orders):
    print("this is phone pe payment")
    
    # 1. PhonePe Authentication
    auth_url = "https://api-preprod.phonepe.com/apis/pg-sandbox/v1/oauth/token"
    auth_payload = {
        "client_version": 1,
        "grant_type": "client_credentials",
        "client_id": "M23KQHM53S73C_2512240944",
        "client_secret": "NDk3MzcyNzUtMjYxNi00MjE1LWExYzMtMDdkZTY2OWJkYWI2"
    }
    auth_headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    access_token = None
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.post(auth_url, data=auth_payload, headers=auth_headers)
            if auth_response.status_code == 200:
                token_data = auth_response.json()
                access_token = token_data.get("access_token")
                print(f"PhonePe Access Token acquired")
            else:
                print(f"PhonePe Auth Failed: {auth_response.text}")
    except Exception as e:
        print(f"Error fetching PhonePe token: {e}")

    if not access_token:
        # Fallback for development if needed, or raise exception
        raise HTTPException(status_code=500, detail="Failed to authenticate with PhonePe")

    # 2. Create order on PhonePe
    order_url = "https://api-preprod.phonepe.com/apis/pg-sandbox/checkout/v2/sdk/order"
    
    # Calculate amount in paisa (e.g., ₹10 = 1000 paisa)
    total_amount = sum(float(order.total) for order in orders)
    amount_in_paisa = int(round(total_amount * 100))
    
    # Use parent_order_id from our database
    parent_order_id = orders[0].parent_order_id if orders else None
    
    order_payload = {
        "merchantOrderId": parent_order_id,
        "amount": amount_in_paisa,
        "expireAfter": 1200,
        "paymentFlow": {
            "type": "PG_CHECKOUT"
        }
    }
    
    order_headers = {
        "Content-Type": "application/json",
        "Authorization": f"O-Bearer {access_token}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            order_response = await client.post(order_url, json=order_payload, headers=order_headers)
            print(f"PhonePe Order Response: {order_response.text}")
            
            if order_response.status_code == 200:
                resp_data = order_response.json()
                # resp_data contains: orderId, state, expireAt, token
                return {
                    "orderId": resp_data.get("orderId"),
                    "merchantId": parent_order_id,
                    "token": resp_data.get("token"),
                    "paymentMode": {"type": "PAY_PAGE"}
                }
            else:
                print(f"PhonePe Order Creation Failed: {order_response.status_code} - {order_response.text}")
                raise HTTPException(status_code=order_response.status_code, detail="PhonePe order creation failed")
                
    except Exception as e:
        print(f"Error creating PhonePe order: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"PhonePe integration error: {str(e)}")

@router.post("/", status_code=status.HTTP_201_CREATED)
async def place_order(
    order_data: OrderCreateSchema,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis),
    order_type: str = Query("combined", description="Order type: combined, split, or urgent")
):
    """
    STEP 1: Create orders based on type (combined/split/urgent)
    STEP 2: Return payment session_id and cf_order_id if payment method is Cashfree
    STEP 3: Orders progress only after successful payment
    
    Order Types:
    - combined: Single order per vendor group. Requires vendor confirmation before rider offer.
    - split: One order per vendor. Each vendor confirms independently.
    - urgent: One order per urgent vendor. Auto-assigns rider after vendor confirmation.
    """
    service = OrderService()
    try:
        # Validate order type
        if order_type not in ["combined", "split", "urgent"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid order type. Must be 'combined', 'split', or 'urgent'"
            )

        # Create orders based on type
        orders = await service.create_orders(
            order_data,
            current_user,
            order_type=order_type
        )

        payment_method = order_data.payment_method.type
        if hasattr(payment_method, 'value'):
            payment_method = payment_method.value
        payment_method = str(payment_method)
        
        requires_payment = payment_method.lower() in ["cashfree", "phonepe"]
        
        # Calculate total amount across all orders
        total_amount = sum(float(order.total) for order in orders)

        # Get parent_order_id from the first order
        parent_order_id = orders[0].parent_order_id if orders else None

        # Build order summaries
        order_summaries = [
            {
                "order_id": order.id,
                "vendor_id": order.vendor_id,
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "tracking_number": order.tracking_number,
                "total": float(order.total),
                "order_type": order.delivery_type
            }
            for order in orders
        ]

        response_data = {
            "success": True,
            "message": f"{len(orders)} order(s) created successfully ({order_type.upper()})",
            "data": {
                "orders": order_summaries,
                "total_amount": total_amount,
                "payment_status": "unpaid",
                "requires_payment": requires_payment,
                "parent_order_id": parent_order_id,
                "order_type": order_type
            }
        }

        if requires_payment:
            # Generate payment session
            try:
                if payment_method.lower() == "phonepe":
                    payment_response = await handle_phonepe_payment(orders)
                else:
                    payment_response = await create_payment_session_for_orders(orders)
                
                
                # Update all orders with payment session info
                for order in orders:
                    if payment_method.lower() == "phonepe":
                        order.payment_session_id = payment_response.get("token")
                        order.cf_order_id = payment_response.get("orderId")
                        order.parent_order_id = payment_response.get("merchantId")
                    else:
                        order.payment_session_id = payment_response["payment_session_id"]
                        order.cf_order_id = payment_response["cf_order_id"]
                        order.parent_order_id = payment_response["order_id"]
                    await order.save()
                
                if payment_method.lower() == "phonepe":
                    return payment_response
                
                # Update the parent_order_id in response data if it changed (though it shouldn't for consistency, 
                # but payment_response["order_id"] likely generates a NEW ID which overwrites the one from service.
                # Let's trust payment_helper logic for online payments, but for COD we stick to service one)
                response_data["data"]["parent_order_id"] = payment_response["order_id"]
                response_data["message"] = f"{len(orders)} order(s) created ({order_type.upper()}). Please complete payment to proceed."

                print(f"[ORDER] Payment session created for {len(orders)} orders (parent: {payment_response['order_id']})")

            except Exception as e:
                print(f"[ERROR] Payment session creation error: {e}")
                response_data["message"] = f"{len(orders)} order(s) created but payment session generation failed."
        else:
            # COD orders - notify vendors immediately
            for order in orders:
                payload = {
                    "type": "order_placed",
                    "order_id": order.id,
                    "parent_order_id": parent_order_id,
                    "customer_name": current_user.name,
                    "payment_method": "COD",
                    "order_type": order_type,
                    "created_at": datetime.utcnow().isoformat()
                }

                try:
                    await redis.publish("order_updates", json.dumps(payload))
                    await manager.send_to(payload, "customers", str(current_user.id), "notifications")

                    # Notify vendor
                    vendor = await VendorProfile.get_or_none(user_id=order.vendor_id)
                    if vendor:
                        await manager.send_to(payload, "vendors", str(vendor.user_id), "notifications")
                        await send_notification(
                            vendor.user_id,
                            f"New {order_type.upper()} Order",
                            f"Order #{order.id} received - {len(order.items)} items"
                        )

                    print(f"[ORDER] {order_type.upper()} order {order.id} notified to vendor")

                except Exception as e:
                    print(f"[ERROR] Notification error for order {order.id}: {e}")

        return response_data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Order creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")


# ============================================================
# 2. GET ALL ORDERS (with filters and pagination)
# ============================================================

@router.get("/")
async def get_all_orders(
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, processing, confirmed, etc."),
    payment_status: Optional[str] = Query(None, description="Filter by payment status: unpaid, paid, failed"),
    order_type_filter: Optional[str] = Query(None, description="Filter by order type: combined, split, urgent"),
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

    # Apply order type filter
    if order_type_filter:
        if order_type_filter not in ["combined", "split", "urgent"]:
            raise HTTPException(status_code=400, detail=f"Invalid order type: {order_type_filter}")
        # Filter by metadata order_type
        # Note: This assumes metadata contains order_type; adjust if needed
        query = query.filter(metadata__order_type=order_type_filter)

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

        # Rider info
        rider_info = None
        order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        if order_status.lower() == "outfordelivery" and order.rider:
            rider_info = {
                "rider_id": order.rider.user_id,
                "rider_name": order.rider.user.name,
                "rider_phone": order.rider.user.phone,
                "rider_image": order.rider.profile_image
            }

        # Vendor info
        vendor_info = None
        if order.metadata and "vendor_info" in order.metadata:
            vendor_info = order.metadata["vendor_info"]
        elif order.vendor:
            vendor_info = {
                "vendor_id": order.vendor_id,
                "vendor_name": order.vendor.name
            }

        # Get order type
        order_type = "combined"
        if order.metadata and "order_type" in order.metadata:
            order_type = order.metadata["order_type"]

        results.append({
            "order_id": order.id,
            "parent_order_id": order.parent_order_id,
            "user_id": str(order.user_id),
            "vendor_id": order.vendor_id,
            "items": items,
            "shipping_address": shipping_address,
            "delivery_option": delivery_option,
            "payment_method": payment_method,
            "subtotal": float(order.subtotal),
            "delivery_fee": float(order.delivery_fee),
            "discount": float(order.discount),
            "total": float(order.total),
            "coupon_code": order.coupon_code,
            "order_date": order.order_date.isoformat(),
            "status": order_status,
            "payment_status": order.payment_status,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery.isoformat() if order.estimated_delivery else None,
            "rider_info": rider_info,
            "vendor_info": vendor_info,
            "order_type": order_type,
            "is_combined": order.is_combined
        })

    return {
        "success": True,
        "data": results,
        "pagination": {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "returned": len(results)
        }
    }


# ============================================================
# 3. GET SINGLE ORDER
# ============================================================

@router.get("/{order_id}")
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific order by ID"""
    order = await Order.get_or_none(id=order_id).prefetch_related(
        'user', 'items__item', 'rider__user', 'vendor'
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization check
    if not (current_user.id == order.user_id or current_user.is_staff):
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    # Build response (similar to get_all_orders but with full detail)
    shipping_address = None
    if order.metadata and "shipping_address" in order.metadata:
        shipping_address = order.metadata["shipping_address"]

    delivery_option = order.metadata.get("delivery_option", {}) if order.metadata else {}
    payment_method = order.metadata.get("payment_method", {}) if order.metadata else {}
    vendor_info = order.metadata.get("vendor_info", {}) if order.metadata else {}

    items = []
    for order_item in order.items:
        items.append({
            "item_id": order_item.item_id,
            "title": order_item.title,
            "price": order_item.price,
            "quantity": order_item.quantity,
            "image_path": order_item.image_path
        })

    order_type = "combined"
    if order.metadata and "order_type" in order.metadata:
        order_type = order.metadata["order_type"]

    return {
        "success": True,
        "data": {
            "order_id": order.id,
            "parent_order_id": order.parent_order_id,
            "order_type": order_type,
            "user_id": str(order.user_id),
            "vendor_id": order.vendor_id,
            "vendor_name": order.vendor.name if order.vendor else None,
            "items": items,
            "shipping_address": shipping_address,
            "delivery_option": delivery_option,
            "payment_method": payment_method,
            "vendor_info": vendor_info,
            "subtotal": float(order.subtotal),
            "delivery_fee": float(order.delivery_fee),
            "discount": float(order.discount),
            "total": float(order.total),
            "coupon_code": order.coupon_code,
            "order_date": order.order_date.isoformat(),
            "status": order.status.value if hasattr(order.status, 'value') else order.status,
            "payment_status": order.payment_status,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery.isoformat() if order.estimated_delivery else None,
            "is_combined": order.is_combined,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat()
        }
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