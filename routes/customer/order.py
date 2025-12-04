import httpx
from applications.customer.services import OrderService
from fastapi import APIRouter, HTTPException, Query, status, Depends
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


@router.get("/{order_id}", response_model=OrderResponseSchema)
async def get_order_details(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get order details with rider info if status is OUT_FOR_DELIVERY"""
    
    order = await Order.get_or_none(id=order_id).prefetch_related(
        'user',
        'items__item',
        'rider__user'  # Fetch rider relationship
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check authorization
    if order.user_id != current_user.id and not current_user.is_staff:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    
    # Get vendors locations
    vendors_locations = await order.get_all_vendors_locations()
    
    # Prepare response
    response_data = {
        "id": order.id,
        "user_id": order.user_id,
        "items": [],
        "shipping_address": order.metadata.get("shipping_address") if order.metadata else None,
        "delivery_option": order.metadata.get("delivery_option", {}) if order.metadata else {},
        "payment_method": order.metadata.get("payment_method", {}) if order.metadata else {},
        "subtotal": order.subtotal,
        "delivery_fee": order.delivery_fee,
        "total": order.total,
        "coupon_code": order.coupon_code,
        "discount": order.discount,
        "order_date": order.order_date,
        "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "metadata": order.metadata,
        "vendors": vendors_locations,
        "payment_status": order.payment_status,
        "rider_info": None
    }
    
    # FIXED: Include rider info only if status is OUT_FOR_DELIVERY
    order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
    if order_status.lower() == "outfordelivery" and order.rider:
        await order.fetch_related('rider__user')
        response_data["rider_info"] = {
            "rider_id": order.rider.id,
            "rider_name": order.rider.user.name,
            "rider_phone": order.rider.user.phone,
            "rider_image": order.rider.profile_image
        }
    
    # Add payment link if order is pending payment
    if order.payment_status == "unpaid" and order.metadata:
        cashfree_data = order.metadata.get("cashfree", {})
        if cashfree_data.get("payment_link"):
            response_data["payment_link"] = cashfree_data["payment_link"]
    
    # Populate items
    for order_item in order.items:
        response_data["items"].append({
            "item_id": order_item.item_id,
            "title": order_item.title,
            "price": order_item.price,
            "quantity": order_item.quantity,
            "image_path": order_item.image_path
        })
    
    return response_data

@router.get("/", status_code=status.HTTP_200_OK, response_model=List[OrderResponseSchema])
async def get_all_orders(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    Get all orders for the current user
    """
    service = OrderService()
    try:
        result = await service.get_all_orders(current_user, skip, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving orders: {str(e)}")


# @router.get("/{order_id}", status_code=status.HTTP_200_OK, response_model=OrderResponseSchema)
# async def get_order(
#     order_id: str,
#     current_user: User = Depends(get_current_user)
# ):
#     """
#     Get a specific order by ID
#     """
#     service = OrderService()
#     try:
#         order = await service.get_order_by_id(order_id, current_user)
#         return order
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving order: {str(e)}")


@router.patch("/{order_id}", status_code=status.HTTP_200_OK)
async def update_order(
    order_id: str,
    update_data: OrderUpdateSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Update order details (only for pending orders)
    """
    service = OrderService()
    try:
        order = await service.update_order(order_id, update_data, current_user)
        return {
            "success": True,
            "message": "Order updated successfully",
            "data": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating order: {str(e)}")


@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
async def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Cancel an order (only for pending orders)
    """
    service = OrderService()
    try:
        order = await service.cancel_order(order_id, current_user)
        return {
            "success": True,
            "message": "Order cancelled successfully",
            "data": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling order: {str(e)}")
    


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
            "return_url": f"{settings.FRONTEND_URL}/payment-status?order_id={order.id}"
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

