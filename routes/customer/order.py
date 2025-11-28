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

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def place_order(
    order_data: OrderCreateSchema, 
    current_user: User = Depends(get_current_user)
):
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        order = await service.create_order(order_data, current_user)
        
        # Extract delivery and payment info from metadata
        delivery_info = order.metadata.get('delivery_option', {})
        payment_info = order.metadata.get('payment_method', {})
        
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


@router.get("/{order_id}", status_code=status.HTTP_200_OK)
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific order by ID"""
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        order = await service.get_order_by_id(order_id, current_user)
        return {
            "success": True,
            "message": "Order retrieved successfully",
            "data": order
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving order: {str(e)}")


@router.get("/", status_code=status.HTTP_200_OK)
async def get_all_orders(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """Get all orders for the current user"""
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        result = await service.get_all_orders(current_user, skip, limit)
        return {
            "success": True,
            "message": "Orders retrieved successfully",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving orders: {str(e)}")


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
