from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
from applications.user.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
from applications.user.customer import CustomerProfile
# Import schemas
from app.token import get_current_user

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/")
async def list_orders(
    user_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    """List all orders for current user"""
    skip = (page - 1) * page_size
    orders = await Order.filter(user_id=user_id).prefetch_related(
        "items", "shipping_address", "delivery_option", "payment_method"
    ).offset(skip).limit(page_size)
    
    total = await Order.filter(user_id=user_id).count()
    
    orders_data = []
    for order in orders:
        items = await OrderItem.filter(order=order)
        orders_data.append({
            "order_id": order.order_id,
            "user_id": order.user_id,
            "subtotal": float(order.subtotal),
            "delivery_fee": float(order.delivery_fee),
            "total": float(order.total),
            "discount": float(order.discount),
            "status": order.status,
            "order_date": order.order_date,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery
        })
    
    return {
        "success": True,
        "message": "Orders retrieved successfully",
        "data": orders_data,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{order_id}/")
async def get_order(order_id: str):
    """Get specific order details"""
    order = await Order.filter(order_id=order_id).prefetch_related(
        "items", "shipping_address", "delivery_option", "payment_method"
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    items = await OrderItem.filter(order=order)
    
    return {
        "success": True,
        "message": "Order retrieved successfully",
        "data": {
            "order_id": order.order_id,
            "user_id": order.user_id,
            "items": [
                {
                    "item_id": item.item_id,
                    "title": item.title,
                    "price": item.price,
                    "quantity": item.quantity,
                    "image_path": item.image_path
                }
                for item in items
            ],
            "subtotal": float(order.subtotal),
            "delivery_fee": float(order.delivery_fee),
            "total": float(order.total),
            "discount": float(order.discount),
            "status": order.status,
            "order_date": order.order_date,
            "tracking_number": order.tracking_number
        }
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def place_order(order_data: OrderCreateSchema):
    """Place a new order"""
    from applications.customer.services import OrderService
    service = OrderService()
    order = await service.create_order(order_data)
    
    return {
        "success": True,
        "message": "Order placed successfully",
        "data": {
            "order_id": order.order_id,
            "status": order.status,
            "tracking_number": order.tracking_number,
            "total": float(order.total)
        }
    }


@router.delete("/{order_id}/")
async def cancel_order(order_id: str):
    """Cancel an order"""
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        order = await service.cancel_order(order_id)
        return {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {"order_id": order.order_id, "status": order.status}
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# # ==================== Dashboard Routes ====================

# dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# @dashboard_router.get("/stats/")
# async def get_dashboard_stats():
#     """Get all dashboard statistics (Admin only)"""
#     total_users = await User.all().count()
#     total_orders = await Order.all().count()
#     total_products = await Product.all().count()
    
#     return {
#         "success": True,
#         "message": "Dashboard statistics retrieved successfully",
#         "data": {
#             "total_users": total_users,
#             "total_orders": total_orders,
#             "total_products": total_products,
#             "total_revenue": 0.0  # Calculate from orders
#         }
#     }