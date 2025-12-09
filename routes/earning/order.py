from fastapi import APIRouter, Form, HTTPException, Depends
from app.auth import permission_required, vendor_required
from applications.user.models import User

from applications.customer.models import Order, OrderItem, OrderStatus
from applications.items.models import Item

router = APIRouter(prefix="/order", tags=["Order Management"])


# ----------------------- FORMATTER -----------------------
def format_float(value):
    return f"{float(value):.2f}" if value is not None else None


# ----------------------- SERIALIZE ITEM -----------------------
async def serialize_item(item: Item):
    await item.fetch_related("category", "subcategory", "sub_subcategory", "vendor__vendor_profile")

    vendor = item.vendor
    vendor_profile = getattr(vendor, "vendor_profile", None)

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
        "vendor_id": vendor.id if vendor else None,
        "shop_image": vendor_profile.photo if vendor_profile else None,
        "shop_name": vendor.name if vendor else None,
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
    vendor = item.vendor if item else None
    vendor_profile = getattr(vendor, "vendor_profile", None)

    return {
        "order_item_id": order_item.id,
        "order_id": order_item.order_id,
        "quantity": order_item.quantity,
        "price": format_float(order_item.price),
        "title": order_item.title,
        "image": order_item.image_path,
        # "item_details": await serialize_item(item) if item else None
    }


# ----------------------- SERIALIZE ORDER -----------------------
async def serialize_order(order: Order):
    await order.fetch_related(
        "items__item__vendor__vendor_profile",
        "user",
        "rider",
        "shipping_address"
    )

    items = [await serialize_order_item(oi) for oi in order.items]

    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "user_name": getattr(order.user, "name", None),
        "rider_id": order.rider_id,
        "vendor_id": order.vendor_id,
        "shipping_address": {
            "id": order.shipping_address.id,
            "address": getattr(order.shipping_address, "address", None),
            "city": getattr(order.shipping_address, "city", None),
            "postal_code": getattr(order.shipping_address, "postal_code", None),
        } if order.shipping_address else None,

        "delivery_type": order.delivery_type.value if order.delivery_type else None,
        "payment_method": order.payment_method.value if order.payment_method else None,
        "subtotal": format_float(order.subtotal),
        "delivery_fee": format_float(order.delivery_fee),
        "total": format_float(order.total),
        "discount": format_float(order.discount),
        "coupon_code": order.coupon_code,
        "status": order.status.value if hasattr(order.status, "value") else order.status,
        "transaction_id": order.transaction_id,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "payment_status": order.payment_status,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "items": items
    }


@router.post("/manage-order-status", dependencies=[Depends(vendor_required)])
async def order_status_management(
    order_id: str = Form(...),
    status: str = Form(..., description="New status for the order 'confirmed', 'shipped', 'outForDelivery', 'cancelled', 'refunded'"),
    vendor: User = Depends(vendor_required)
):
    # Fetch the order belonging to this vendor
    order = await Order.get_or_none(id=order_id, vendor_id=vendor.id)
    print("Vendor making the request:", vendor)
    print("Vendor making the request:", vendor.id)
    print("Order making the request:", order.vendor_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Validate status against OrderStatus enum
    allowed_statuses = [
        "confirmed",
        "shipped",
        "outForDelivery",
        "cancelled",
        "refunded"
    ]
    
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid order status")

    try:
        new_status = OrderStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order status")

    order.status = new_status
    await order.save(update_fields=["status"])

    return {
        "success": True,
        "message": "Order status updated successfully",
        "order_id": order.id,
        "status": order.status.value
    }


# ----------------------- GET ALL ORDERS -----------------------
@router.get("/my_orders", summary="Get full details of all orders with their items",)
async def get_all_orders(vendor: User = Depends(vendor_required)):
    orders = await Order.filter(vendor_id=vendor.id).prefetch_related(
        "items__item__vendor__vendor_profile",
        "user",
        "rider",
        "shipping_address"
    )

    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")

    return {
        "total_orders": len(orders),
        "orders": [await serialize_order(order) for order in orders]
    }

# ----------------------- GET ALL ORDERS -----------------------
@router.get(
    "/all_orders",
    summary="Get full details of all orders with their items only superadmin can access",
    dependencies=[Depends(permission_required("view_order"))]
)
async def get_all_orders():
    orders = await Order.all().prefetch_related(
        "items__item__vendor__vendor_profile",
        "user",
        "rider",
        "shipping_address"
    )

    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")

    return {
        "total_orders": len(orders),
        "orders": [await serialize_order(order) for order in orders]
    }


# ----------------------- GET SINGLE ORDER -----------------------
@router.get("/{order_id}", summary="Get full order details with all items")
async def get_order_details(order_id: str, vendor: User = Depends(vendor_required)):
    order = await Order.filter(id=order_id, vendor_id=vendor.id).prefetch_related(
        "items__item__vendor__vendor_profile",
        "user",
        "rider",
        "shipping_address"
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return await serialize_order(order)
