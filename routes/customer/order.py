from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
from applications.user.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
# Import schemas
from app.token import get_current_user
from applications.user.customer import *

router = APIRouter(prefix="/orders", tags=["Orders"])



@router.get("/{order_id}", response_model=OrderResponseSchema)
async def get_order(
    order_id: str,
    current_user = Depends(get_current_user)
):
    """Get a specific order"""
    order = await Order.get(id=order_id).prefetch_related("shipping_address", "user", "cart", "items")
    
    # Check if order belongs to current user
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    
    return {
        "order_id": order.id,  # ✅ Changed from order.order_id
        "user_id": str(order.user_id),
        "items": [
                OrderItemResponseSchema.from_orm(item) 
                for item in order.items
            ] if hasattr(order, 'items') else [],
        "shipping_address": order.shipping_address,
        "delivery_option": order.delivery_type,  # ✅ Changed from delivery_option
        "payment_method": order.payment_method,
        "subtotal": order.subtotal,
        "delivery_fee": order.delivery_fee,
        "total": order.total,
        "coupon_code": order.coupon_code,
        "discount": order.discount,
        "order_date": order.order_date,
        "status": order.status,
        "transaction_id": order.transaction_id,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "metadata": order.metadata
    }


@router.get("/", response_model=List[OrderResponseSchema])
async def get_orders(
    current_user = Depends(get_current_user)
):
    """Get all orders for current user"""
    orders = await Order.filter(user=current_user.id).prefetch_related("shipping_address", "items")
    
    result = []
    for order in orders:
        result.append({
            "order_id": order.id,
            "user_id": str(order.user_id),
            "items": [
                OrderItemResponseSchema.from_orm(item) 
                for item in order.items
            ] if hasattr(order, 'items') else [],
            "shipping_address": ShippingAddressResponseSchema.from_orm(order.shipping_address) if order.shipping_address else None,
            "delivery_option": order.delivery_type.value,  # ✅ Get enum value
            "payment_method": order.payment_method.value,  # ✅ Get enum value
            "subtotal": order.subtotal,
            "delivery_fee": order.delivery_fee,
            "total": order.total,
            "coupon_code": order.coupon_code,
            "discount": order.discount,
            "order_date": order.order_date,
            "status": order.status.value,  # ✅ Get enum value
            "transaction_id": order.transaction_id,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery,
            "metadata": order.metadata
        })
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def place_order(order_data: OrderCreateSchema , current_user: User = Depends(get_current_user)):
    """Place a new order"""
    from applications.customer.services import OrderService
    service = OrderService()
    order = await service.create_order(order_data, current_user)
    
    return {
        "success": True,
        "message": "Order placed successfully",
        "data": {
            "order_id": order.id,
            "status": order.status,
            "tracking_number": order.tracking_number,
            "total": float(order.total)
        }
    }


@router.delete("/{order_id}/")
async def cancel_order(order_id: str, current_user = Depends(get_current_user)):
    """Cancel an order"""
    from applications.customer.services import OrderService
    service = OrderService()
    
    try:
        order = await service.cancel_order(order_id)
        return {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {"id": order.id, "status": order.status}
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# # # ==================== Dashboard Routes ====================

# # dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# # @dashboard_router.get("/stats/")
# # async def get_dashboard_stats():
# #     """Get all dashboard statistics (Admin only)"""
# #     total_users = await User.all().count()
# #     total_orders = await Order.all().count()
# #     total_products = await Product.all().count()
    
# #     return {
# #         "success": True,
# #         "message": "Dashboard statistics retrieved successfully",
# #         "data": {
# #             "total_users": total_users,
# #             "total_orders": total_orders,
# #             "total_products": total_products,
# #             "total_revenue": 0.0  # Calculate from orders
# #         }
# #     }