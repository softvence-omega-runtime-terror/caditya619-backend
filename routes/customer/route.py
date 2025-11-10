from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
# from applications.customer.schemas import CartCreateSchema
from applications.user.models import User
# from applications.customer.models import Cart, CartItem

# Import schemas
from app.token import get_current_user





# ==================== Cart Routes ====================

router = APIRouter(prefix="/carts", tags=["Carts"])

@router.get("/hello")
async def list_carts():
    return {"message": "List of carts"}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_cart(current_user: User = Depends(get_current_user)):
    # cart = await Cart.create(
    #     user=current_user
    # )
    
    # return {
    #     "success": True,
    #     "message": "Cart created successfully",
    #     "data": {
    #         "id": cart.id,
    #         "user_id": cart.user_id,
    #         "items": [],
    #         "created_at": cart.created_at
    #     }
    # }
    return {"message": current_user.name}


# @router.get("/{cart_id}/")
# async def get_cart(cart_id: str):
#     """Get cart details"""
#     cart = await Cart.filter(id=cart_id).prefetch_related("items").first()
#     if not cart:
#         raise HTTPException(status_code=404, detail="Cart not found")
    
#     items = await CartItem.filter(cart=cart).prefetch_related("product")
    
#     return {
#         "success": True,
#         "message": "Cart retrieved successfully",
#         "data": {
#             "id": cart.id,
#             "user_id": cart.user_id,
#             "items": [
#                 {
#                     "id": item.id,
#                     "product_id": item.product_id,
#                     "quantity": item.quantity,
#                     "added_at": item.added_at
#                 }
#                 for item in items
#             ],
#             "created_at": cart.created_at
#         }
#     }


# @router.delete("/{cart_id}/")
# async def delete_cart(cart_id: str):
#     """Delete cart"""
#     cart = await Cart.filter(id=cart_id).first()
#     if not cart:
#         raise HTTPException(status_code=404, detail="Cart not found")
    
#     await cart.delete()
    
#     return {
#         "success": True,
#         "message": "Cart deleted successfully"
#     }


# @router.post("/{cart_id}/items/", status_code=status.HTTP_201_CREATED)
# async def add_cart_item(cart_id: str, item_data: CartItemCreateSchema):
#     """Add item to cart"""
#     cart = await Cart.filter(id=cart_id).first()
#     if not cart:
#         raise HTTPException(status_code=404, detail="Cart not found")
    
#     product = await Product.filter(id=item_data.product_id).first()
#     if not product:
#         raise HTTPException(status_code=404, detail="Product not found")
    
#     # Check if item already exists
#     existing_item = await CartItem.filter(cart=cart, product=product).first()
#     if existing_item:
#         existing_item.quantity += item_data.quantity
#         await existing_item.save()
#         item = existing_item
#     else:
#         item = await CartItem.create(
#             id=f"item_{int(datetime.utcnow().timestamp())}",
#             cart=cart,
#             product=product,
#             quantity=item_data.quantity
#         )
    
#     return {
#         "success": True,
#         "message": "Item added to cart",
#         "data": {
#             "id": item.id,
#             "product_id": item.product_id,
#             "quantity": item.quantity,
#             "added_at": item.added_at
#         }
#     }


# @router.patch("/{cart_id}/items/{item_id}/")
# async def update_cart_item(cart_id: str, item_id: str, item_data: CartItemUpdateSchema):
#     """Update cart item quantity"""
#     item = await CartItem.filter(id=item_id, cart_id=cart_id).first()
#     if not item:
#         raise HTTPException(status_code=404, detail="Cart item not found")
    
#     item.quantity = item_data.quantity
#     await item.save()
    
#     return {
#         "success": True,
#         "message": "Cart item updated",
#         "data": {
#             "id": item.id,
#             "quantity": item.quantity
#         }
#     }


# @router.delete("/{cart_id}/items/{item_id}/")
# async def delete_cart_item(cart_id: str, item_id: str):
#     """Remove item from cart"""
#     item = await CartItem.filter(id=item_id, cart_id=cart_id).first()
#     if not item:
#         raise HTTPException(status_code=404, detail="Cart item not found")
    
#     await item.delete()
    
#     return {
#         "success": True,
#         "message": "Item removed from cart"
#     }


# # ==================== Order Routes ====================

# order_router = APIRouter(prefix="/customer/orders", tags=["Orders"])


# @order_router.get("/")
# async def list_orders(
#     user_id: str = Query(...),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100)
# ):
#     """List all orders for current user"""
#     skip = (page - 1) * page_size
#     orders = await Order.filter(user_id=user_id).prefetch_related(
#         "items", "shipping_address", "delivery_option", "payment_method"
#     ).offset(skip).limit(page_size)
    
#     total = await Order.filter(user_id=user_id).count()
    
#     orders_data = []
#     for order in orders:
#         items = await OrderItem.filter(order=order)
#         orders_data.append({
#             "order_id": order.order_id,
#             "user_id": order.user_id,
#             "subtotal": float(order.subtotal),
#             "delivery_fee": float(order.delivery_fee),
#             "total": float(order.total),
#             "discount": float(order.discount),
#             "status": order.status,
#             "order_date": order.order_date,
#             "tracking_number": order.tracking_number,
#             "estimated_delivery": order.estimated_delivery
#         })
    
#     return {
#         "success": True,
#         "message": "Orders retrieved successfully",
#         "data": orders_data,
#         "total": total,
#         "page": page,
#         "page_size": page_size
#     }


# @order_router.get("/{order_id}/")
# async def get_order(order_id: str):
#     """Get specific order details"""
#     order = await Order.filter(order_id=order_id).prefetch_related(
#         "items", "shipping_address", "delivery_option", "payment_method"
#     ).first()
    
#     if not order:
#         raise HTTPException(status_code=404, detail="Order not found")
    
#     items = await OrderItem.filter(order=order)
    
#     return {
#         "success": True,
#         "message": "Order retrieved successfully",
#         "data": {
#             "order_id": order.order_id,
#             "user_id": order.user_id,
#             "items": [
#                 {
#                     "product_id": item.product_id,
#                     "title": item.title,
#                     "price": item.price,
#                     "quantity": item.quantity,
#                     "image_path": item.image_path
#                 }
#                 for item in items
#             ],
#             "subtotal": float(order.subtotal),
#             "delivery_fee": float(order.delivery_fee),
#             "total": float(order.total),
#             "discount": float(order.discount),
#             "status": order.status,
#             "order_date": order.order_date,
#             "tracking_number": order.tracking_number
#         }
#     }


# @order_router.post("/", status_code=status.HTTP_201_CREATED)
# async def place_order(order_data: OrderCreateSchema):
#     """Place a new order"""
#     from applications.customer.services import OrderService
#     service = OrderService()
#     order = await service.create_order(order_data)
    
#     return {
#         "success": True,
#         "message": "Order placed successfully",
#         "data": {
#             "order_id": order.order_id,
#             "status": order.status,
#             "tracking_number": order.tracking_number,
#             "total": float(order.total)
#         }
#     }


# @order_router.delete("/{order_id}/")
# async def cancel_order(order_id: str):
#     """Cancel an order"""
#     from applications.customer.services import OrderService
#     service = OrderService()
    
#     try:
#         order = await service.cancel_order(order_id)
#         return {
#             "success": True,
#             "message": "Order cancelled successfully",
#             "data": {"order_id": order.order_id, "status": order.status}
#         }
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))


# # ==================== Prescription Routes ====================

# prescription_router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


# @prescription_router.post("/", status_code=status.HTTP_201_CREATED)
# async def upload_prescription(prescription_data: PrescriptionUploadSchema):
#     """Upload a prescription"""
#     user = await User.filter(id=prescription_data.user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     prescription = await Prescription.create(
#         id=f"presc_{int(datetime.utcnow().timestamp())}",
#         user=user,
#         image_path=prescription_data.image_path,
#         file_name=prescription_data.file_name
#     )
    
#     return {
#         "success": True,
#         "message": "Prescription uploaded successfully",
#         "data": {
#             "id": prescription.id,
#             "user_id": prescription.user_id,
#             "image_path": prescription.image_path,
#             "file_name": prescription.file_name,
#             "status": prescription.status,
#             "uploaded_at": prescription.uploaded_at
#         }
#     }


# @prescription_router.get("/{prescription_id}/")
# async def get_prescription(prescription_id: str):
#     """Get prescription with vendor responses"""
#     prescription = await Prescription.filter(id=prescription_id).prefetch_related(
#         "vendor_responses"
#     ).first()
    
#     if not prescription:
#         raise HTTPException(status_code=404, detail="Prescription not found")
    
#     vendor_responses = await VendorResponse.filter(prescription=prescription).prefetch_related("medicines")
    
#     return {
#         "success": True,
#         "message": "Prescription retrieved successfully",
#         "data": {
#             "id": prescription.id,
#             "user_id": prescription.user_id,
#             "image_path": prescription.image_path,
#             "file_name": prescription.file_name,
#             "status": prescription.status,
#             "uploaded_at": prescription.uploaded_at,
#             "vendor_responses": [
#                 {
#                     "id": vr.id,
#                     "vendor_id": vr.vendor_id,
#                     "vendor_name": vr.vendor_name,
#                     "total_amount": float(vr.total_amount),
#                     "status": vr.status
#                 }
#                 for vr in vendor_responses
#             ]
#         }
#     }


# # ==================== Profile Routes ====================

# profile_router = APIRouter(prefix="/customer/profile", tags=["Profile"])


# @profile_router.get("/")
# async def get_profile(user_id: str = Query(...)):
#     """Get user profile"""
#     user = await User.filter(id=user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     return {
#         "success": True,
#         "message": "Profile retrieved successfully",
#         "data": {
#             "id": user.id,
#             "first_name": user.first_name,
#             "last_name": user.last_name,
#             "email": user.email,
#             "phone_number": user.phone_number,
#             "address_1": user.address_1,
#             "address_2": user.address_2,
#             "postal_code": user.postal_code
#         }
#     }


# @profile_router.put("/")
# async def update_profile(user_id: str, profile_data: UserProfileUpdateSchema):
#     """Update user profile"""
#     user = await User.filter(id=user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     if profile_data.first_name:
#         user.first_name = profile_data.first_name
#     if profile_data.last_name:
#         user.last_name = profile_data.last_name
#     if profile_data.phone_number:
#         user.phone_number = profile_data.phone_number
#     if profile_data.address_1:
#         user.address_1 = profile_data.address_1
#     if profile_data.address_2:
#         user.address_2 = profile_data.address_2
#     if profile_data.postal_code:
#         user.postal_code = profile_data.postal_code
    
#     await user.save()
    
#     return {
#         "success": True,
#         "message": "Profile updated successfully"
#     }


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