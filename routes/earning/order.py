from fastapi import  APIRouter, Form, HTTPException, Depends

from app.auth import permission_required
from applications.customer.models import Order


router = APIRouter(prefix='/order', tags=['Order Management'])


@router.post("/manage-order-status", dependencies=[Depends(permission_required('update_order'))])
async def order_status_management(
    order_id: int = None,
    status: str = Form(None),
):
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if status not in ['delivered', 'shipped', 'processing', 'confirmed']:
        raise HTTPException(status_code=404, detail="Enter a valid status.")

    order.status = status
    await order.save(update_fields=["status"])

    return {
        "success": True,
        "message": "Order status updated successfully",
        "order_id": order.id,
        "status": order.status
    }


from fastapi import APIRouter, HTTPException, Depends
from typing import List

from applications.user.models import User
from app.token import get_current_user
from applications.customer.models import Order, OrderItem
from applications.items.models import Item

router = APIRouter(prefix="/orders", tags=["Orders"])


# ----------------------- FORMATTER -----------------------
def format_float(value):
    return f"{float(value):.2f}" if value is not None else None


# ----------------------- SERIALIZE ITEM -----------------------
async def serialize_item(item: Item):
    await item.fetch_related("category", "subcategory", "sub_subcategory", "vendor__vendor_profile")

    vendor = item.vendor
    vendor_profile = vendor.vendor_profile if hasattr(vendor, "vendor_profile") else None

    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "category_id": item.category_id,
        "subcategory_id": item.subcategory_id,
        "sub_subcategory_id": item.sub_subcategory_id,
        "price": format_float(item.price),
        "discount": item.discount,
        "discounted_price": format_float(item.discounted_price),
        "sell_price": format_float(item.sell_price),
        "ratings": item.ratings,
        "total_reviews": await item.get_total_reviews(),
        "ratings_summary": await item.get_rating_summary_percentage(),
        "stock": item.stock,
        "total_sale": item.total_sale,
        "popular": item.popular,
        "free_delivery": item.free_delivery,
        "hot_deals": item.hot_deals,
        "flash_sale": item.flash_sale,
        "weight": item.weight,
        "vendor_id": vendor.id,
        "shop_image": vendor_profile.photo if vendor_profile else None,
        "shop_name": vendor.name,
        "image": item.image,
        "isSignature": item.isSignature,
        "is_in_stock": item.is_in_stock,
        "new_arrival": item.new_arrival,
        "today_deals": item.today_deals,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


# ----------------------- SERIALIZE ORDER ITEM -----------------------
async def serialize_order_item(order_item: OrderItem):
    await order_item.fetch_related("item__vendor__vendor_profile")
    item = order_item.item
    vendor = item.vendor
    vendor_profile = vendor.vendor_profile if hasattr(vendor, "vendor_profile") else None

    return {
        "order_item_id": order_item.id,
        "order_id": order_item.order_id,
        "quantity": order_item.quantity,
        "price": format_float(order_item.price),
        "title": order_item.title,
        "image": order_item.image_path,
        "vendor_id": vendor.id,
        "vendor_name": vendor.name,
        "vendor_image": vendor_profile.photo if vendor_profile else None,
        "item_details": await serialize_item(item)
    }


# ----------------------- SERIALIZE ORDER -----------------------
async def serialize_order(order: Order):
    await order.fetch_related("items__item__vendor__vendor_profile", "user", "rider", "shipping_address")

    items = []
    for order_item in order.items:
        items.append(await serialize_order_item(order_item))

    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "user_name": order.user.name if hasattr(order.user, "name") else None,
        "rider_id": order.rider_id,
        "shipping_address": {
            "id": order.shipping_address.id if order.shipping_address else None,
            "address": getattr(order.shipping_address, "address", None),
            "city": getattr(order.shipping_address, "city", None),
            "postal_code": getattr(order.shipping_address, "postal_code", None)
        } if order.shipping_address else None,
        "delivery_type": order.delivery_type.value if order.delivery_type else None,
        "payment_method": order.payment_method.value if order.payment_method else None,
        "subtotal": format_float(order.subtotal),
        "delivery_fee": format_float(order.delivery_fee),
        "total": format_float(order.total),
        "discount": format_float(order.discount),
        "coupon_code": order.coupon_code,
        "status": order.status.value if order.status else None,
        "transaction_id": order.transaction_id,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "payment_status": order.payment_status,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "items": items
    }




# ----------------------- GET ORDER WITH ITEMS -----------------------
@router.get("/all_orders", summary="Get full details of all orders with their items")
async def get_all_orders():
    # Fetch all orders
    orders = await Order.all().prefetch_related(
        "items__item__vendor__vendor_profile",
        "user",
        "rider",
        "shipping_address"
    )

    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")

    # Serialize all orders
    serialized_orders = []
    for order in orders:
        serialized_orders.append(await serialize_order(order))

    return {
        "total_orders": len(serialized_orders),
        "orders": serialized_orders
    }


# ----------------------- GET ORDER WITH ITEMS -----------------------
@router.get("/{order_id}", summary="Get full order details with all items")
async def get_order_details(order_id: str):
    order = await Order.filter(id=order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return await serialize_order(order)