from fastapi import APIRouter, HTTPException, Query, status, Depends
from datetime import datetime
from applications.user.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
from app.token import get_current_user
from applications.user.customer import *

router = APIRouter(prefix="/carts", tags=["Cart"])

@router.get("/{cart_id}/")
async def get_cart(cart_id: str):
    """Get cart details"""
    cart = await Cart.filter(id=cart_id).prefetch_related("items").first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    items = await CartItem.filter(cart=cart).prefetch_related("item")
    
    return {
        "success": True,
        "message": "Cart retrieved successfully",
        "data": {
            "id": cart.id,
            "user_id": cart.user_id,
            "items": [
                {
                    "id": item.id,
                    "item_id": item.item_id,
                    "quantity": item.quantity,
                    "added_at": item.added_at
                }
                for item in items
            ],
            "created_at": cart.created_at
        }
    }



@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_cart(cart_data: CartCreateSchema, current_user: User = Depends(get_current_user)):
    """Create a new cart"""
    user = await User.filter(id=cart_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cart = await Cart.create(
        id=f"cart_{int(datetime.utcnow().timestamp())}",
        user=user
    )
    
    return {
        "success": True,
        "message": "Cart created successfully",
        "data": {
            "id": cart.id,
            "user_id": cart.user_id,
            "items": [],
            "created_at": cart.created_at
        }
    }


@router.delete("/{cart_id}/")
async def delete_cart(cart_id: str):
    """Delete cart"""
    cart = await Cart.filter(id=cart_id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    await cart.delete()
    
    return {
        "success": True,
        "message": "Cart deleted successfully"
    }


@router.post("/{cart_id}/items/", status_code=status.HTTP_201_CREATED)
async def add_cart_item(cart_id: str, item_data: CartItemCreateSchema):
    """Add item to cart"""
    cart = await Cart.filter(id=cart_id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    item = await Item.filter(id=item_data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    
    # Check if item already exists
    existing_item = await CartItem.filter(cart=cart, item=item).first()
    if existing_item:
        existing_item.quantity += item_data.quantity
        await existing_item.save()
        item = existing_item
    else:
        item = await CartItem.create(
            id=f"item_{int(datetime.utcnow().timestamp())}",
            cart=cart,
            item=item,
            quantity=item_data.quantity
        )
    
    return {
        "success": True,
        "message": "Item added to cart",
        "data": {
            "id": item.id,
            "item_id": item.item_id,
            "quantity": item.quantity,
            "added_at": item.added_at
        }
    }


@router.patch("/{cart_id}/items/{item_id}/")
async def update_cart_item(cart_id: str, item_id: str, item_data: CartItemUpdateSchema):
    """Update cart item quantity"""
    print("Updating cart item: ", cart_id, item_id, item_data)
    item = await CartItem.filter(item=item_id, cart=cart_id).first()
    print("item info: ", item)

    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    item.quantity = item_data.quantity
    await item.save()
    
    return {
        "success": True,
        "message": "Cart item updated",
        "data": {
            "id": item.id,
            "quantity": item.quantity
        }
    }


@router.delete("/{cart_id}/items/{item_id}/")
async def delete_cart_item(cart_id: str, item_id: str):
    """Remove item from cart"""
    item = await CartItem.filter(item=item_id, cart=cart_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    await item.delete()
    
    return {
        "success": True,
        "message": "Item removed from cart"
    }


