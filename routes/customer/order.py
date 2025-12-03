from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
from applications.user.models import *
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from app.token import get_current_user
from app.utils.websocket_manager import manager
from routes.rider.notifications import send_notification
from app.redis import get_redis
import json
from applications.user.vendor import VendorProfile

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def place_order(
    order_data: OrderCreateSchema, 
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        order = await service.create_order(order_data, current_user)
        
        # Extract delivery and payment info from metadata
        delivery_info = order.metadata.get('delivery_option', {})
        payment_info = order.metadata.get('payment_method', {})
        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(404, "Order item not found")
        
        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(404, "Vendor not found")

        payload = {
            "type": "order_placed",
            "order_id": order.id,
            "customer_name": current_user.name,
            "accepted_at": datetime.utcnow().isoformat()
        }
        await redis.publish("order_updates", json.dumps(payload))

        try:
            print("user id", str(current_user.id))
            print("user id", str(vendor.user_id))

            await manager.send_to(payload, "customers", str(current_user.id))
            await manager.send_to(payload, "vendors", str(vendor.user_id))

        except Exception as e:
            print(f"WebSocket send error: {e}")

        try:
            await send_notification(current_user.id, "Place order", f"Your order has been placed with ID: {order.id}")
            await send_notification(vendor.user_id, "New order received", f"A new order has been placed by customer: {current_user.name}")
        except Exception as e:
            print(f"Notification send error: {e}")
        
        return {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": order.id,
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "tracking_number": order.tracking_number,
                "total": float(order.total),
                "delivery_option": {
                    "type": delivery_info.get('type', ''),
                    "title": delivery_info.get('title', ''),
                    "description": delivery_info.get('description', ''),
                    "price": delivery_info.get('price', 0.0)
                },
                "payment_method": {
                    "type": payment_info.get('type', ''),
                    "name": payment_info.get('name', '')
                }
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")


@router.get("/", status_code=status.HTTP_200_OK, response_model=List[OrderResponseSchema])
async def get_all_orders(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    from applications.customer.services import OrderService
    service = OrderService()
    try:
        result = await service.get_all_orders(current_user, skip, limit)
        return result  # Pydantic will validate this matches OrderResponseSchema
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving orders: {str(e)}")

@router.get("/{order_id}", status_code=status.HTTP_200_OK, response_model=OrderResponseSchema)
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    from applications.customer.services import OrderService
    service = OrderService()
    try:
        order = await service.get_order_by_id(order_id, current_user)
        return order  # Pydantic will validate this matches OrderResponseSchema
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving order: {str(e)}")


@router.patch("/{order_id}", status_code=status.HTTP_200_OK)
async def update_order(
    order_id: str,
    update_data: OrderUpdateSchema,
    current_user: User = Depends(get_current_user)
):
    """Update order - only if status is PENDING"""
    from applications.customer.services import OrderService
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
    """Cancel order - only if status is PENDING"""
    from applications.customer.services import OrderService
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