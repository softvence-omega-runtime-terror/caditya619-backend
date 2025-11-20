from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from applications.user.models import User
from applications.user.customer import CustomerShippingAddress, CustomerProfile
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from decimal import Decimal, InvalidOperation
import uuid
import time
from tortoise.models import Model
from fastapi import Depends, HTTPException, status
from tortoise.exceptions import DoesNotExist
# from app.token import get_current_user
# current_user = Depends(get_current_user)

class ShippingAddressService:
    """Service layer for managing customer shipping addresses"""
    
    MAX_ADDRESSES_PER_TYPE = 1  # Only one address per type allowed
    MAX_TOTAL_ADDRESSES = 3  # Maximum 3 addresses total
    
    @staticmethod
    async def validate_address_limit(current_user: int, address_type: str, exclude_id: Optional[str] = None):
        # ... (Validation logic remains the same)
        query = CustomerShippingAddress.filter(user=current_user, addressType=address_type)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        
        existing_type_count = await query.count()
        if existing_type_count >= ShippingAddressService.MAX_ADDRESSES_PER_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You already have a {address_type} address. Each address type can only be added once."
            )

        total_query = CustomerShippingAddress.filter(user=current_user)
        if exclude_id:
            total_query = total_query.exclude(id=exclude_id)
        
        total_count = await total_query.count()
        if total_count >= ShippingAddressService.MAX_TOTAL_ADDRESSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You can only have a maximum of {ShippingAddressService.MAX_TOTAL_ADDRESSES} shipping addresses."
            )
    
    @staticmethod
    async def create_address(current_user: int, address_data: dict):
        # ... (Creation logic remains the same)
        address_type = address_data.get("addressType", "HOME")
        
        await ShippingAddressService.validate_address_limit(current_user, address_type)
        address_id = f"{current_user}_addr_{int(time.time() * 1000)}"
        
        address = await CustomerShippingAddress.create(
            id=address_id,
            user=current_user,
            **address_data
        )
        
        return address
    
    @staticmethod
    async def get_user_addresses(current_user: str, address_type: Optional[str] = None):
        """Get all addresses for a user, optionally filtered by type"""
        
        
        query = CustomerShippingAddress.filter(user=current_user)
        
        if address_type:
            query = query.filter(addressType=address_type)
        
        addresses = await query.all()
        return addresses
    
    @staticmethod
    async def get_address_by_id(address_id: str, current_user: str):
        """Get a specific address by ID"""
        
        try:
            address = await CustomerShippingAddress.get(id=address_id, user=current_user)
            return address
        except DoesNotExist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shipping address not found"
            )
    # @staticmethod
    # async def get_address_by_type(address_type: str, current_user: str):
    #     """Get a specific address by type"""
    #     print("rrrrrrrrrrrrrrrrr ",address_type)



    #     try:
    #         address = await CustomerShippingAddress.get(addressType=address_type, user=current_user)
    #         return address
    #     except DoesNotExist:
    #         raise HTTPException(
    #             status_code=status.HTTP_404_NOT_FOUND,
    #             detail="Shipping address not found"
    #         )
        
    @staticmethod
    async def update_address(address_id: str, current_user: str, update_data: dict):

        address = await ShippingAddressService.get_address_by_id(address_id, current_user)
        
        if "is_default" in update_data and update_data["is_default"]:
            # FIX: Remove addressType filter to unset all other defaults
            await CustomerShippingAddress.filter( 
                user=current_user,
                is_default=True
            ).exclude(id=address_id).update(is_default=False)
        
        for field, value in update_data.items():
            if value is not None:
                setattr(address, field, value)
        
        await address.save()
        return address
    
    @staticmethod
    async def delete_address(address_id: str, current_user: str):
        """Delete a shipping address"""
        
        
        address = await ShippingAddressService.get_address_by_id(address_id, current_user)
        
        was_default = address.is_default
        address_type = address.addressType
        
        await address.delete()
        
        # If deleted address was default, set another as default
        if was_default:
            remaining = await CustomerShippingAddress.filter(
                user=current_user,
                addressType=address_type
            ).first()
            
            if remaining:
                remaining.is_default = True
                await remaining.save()
        
        return {"message": "Address deleted successfully"}
    
    @staticmethod
    async def set_default_address(address_id: str, current_user: str):
        
        address = await ShippingAddressService.get_address_by_id(address_id, current_user)
        
        # FIX: Remove addressType filter to unset all other defaults
        # Unset other defaults for this user (regardless of address type)
        await CustomerShippingAddress.filter(
            user=current_user,
            is_default=True
        ).exclude(id=address_id).update(is_default=False)
        
        # Set this as default
        address.is_default = True
        await address.save()
        
        return address
    
    @staticmethod
    async def get_default_address(current_user: str, address_type: str):
        """Get the default address for a specific type"""
        
        
        address = await CustomerShippingAddress.filter(
            user=current_user,
            addressType=address_type,
            is_default=True
        ).first()
        
        if not address:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No default {address_type} address found"
            )
        
        return address



class OrderService:
    
    @staticmethod
    def _generate_order_id() -> str:
        """Generate unique order ID"""
        return f"ORD_{uuid.uuid4().hex[:8].upper()}"

    async def create_order(self, order_data: OrderCreateSchema, current_user) -> Order:
        """Create a new order"""
        subtotal = Decimal("0")
        order_items = []
        
        user = current_user
        user_id = user.id
        
        # Process cart items
        for cart_data in order_data.carts:
            cart = await Cart.get(id=cart_data.cart_id).prefetch_related('items__item')
            
            for cart_item in cart.items:
                try:
                    item = cart_item.item
                    price = Decimal(str(item.price))
                    quantity = cart_item.quantity
                    subtotal += price * quantity
                    
                    order_items.append({
                        'item': item,
                        'title': item.title,
                        'price': price,
                        'quantity': quantity,
                        'image_path': getattr(item, 'image', '')
                    })
                    
                except Exception as e:
                    print(f"Error processing cart item: {e}")
                    continue
        
        # Calculate totals
        delivery_fee = Decimal(str(order_data.delivery_option.price))
        discount = self._apply_coupon(subtotal, order_data.coupon_code)
        total = subtotal + delivery_fee - discount
        
        # Create shipping address
        shipping_address_id = f"addr_{int(time.time() * 1000)}"
        shipping_address = await CustomerShippingAddress.create(
            id=shipping_address_id,
            user_id=user_id,
            full_name=order_data.shipping_address.full_name or "",
            address_line1=order_data.shipping_address.address_line1 or "",
            address_line2=order_data.shipping_address.address_line2 or "",
            city=order_data.shipping_address.city or "",
            state=order_data.shipping_address.state or "",
            postal_code=order_data.shipping_address.postal_code or "",
            country=order_data.shipping_address.country or "",
            phone_number=order_data.shipping_address.phone_number or "",
            is_default=order_data.shipping_address.is_default or False
        )
        
        # Generate unique order ID
        order_id = f"order_{int(time.time() * 1000)}"
        
        # ✅ Create the order - matching your model fields
        order = await Order.create(
            id=order_id,  # ✅ Changed from order_id to id
            user_id=user_id,
            cart_id=order_data.carts[0].cart_id if order_data.carts else None,  # ✅ Added cart reference
            shipping_address_id=shipping_address.id,
            delivery_type=order_data.delivery_option.type,  # ✅ Changed to delivery_type enum
            payment_method=order_data.payment_method.type,  # ✅ Changed to payment_method enum
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            coupon_code=order_data.coupon_code,
            discount=discount,
            status=OrderStatus.PENDING,
            tracking_number=self._generate_tracking_number(),
            estimated_delivery=self._calculate_estimated_delivery(
                order_data.delivery_option.type
            ),
            metadata={"created_at": datetime.utcnow().isoformat()}
        )
        
        # Create order items
        for item_data in order_items:
            await OrderItem.create(
                order_id=order.id,
                item_id_id=item_data['item'].id,  # ✅ Note: Tortoise uses field_name_id for ForeignKey
                title=item_data['title'],
                price=str(item_data['price']),  # ✅ Your model has CharField for price
                quantity=item_data['quantity'],
                image_path=item_data['image_path']
            )
        
        # Fetch related data
        await order.fetch_related("shipping_address", "user", "cart")
        
        return order


    def _generate_tracking_number(self) -> str:
        """Generate tracking number"""
        import random
        return f"TRK{random.randint(100000000, 999999999)}"


    def _calculate_estimated_delivery(self, delivery_type: str) -> datetime:
        """Calculate estimated delivery date"""
        days_map = {
            "standard": 5,
            "express": 2,
            "pickup": 1,
            "urgent": 1
        }
        days = days_map.get(delivery_type, 5)
        return datetime.utcnow() + timedelta(days=days)


    @staticmethod
    def _apply_coupon(subtotal: Decimal, coupon_code: Optional[str]) -> Decimal:
        """Apply coupon discount"""
        coupon_discounts = {
            "NEWUSER50": Decimal("50.0"),
            "SAVE20": Decimal("20.0"),
            "WELCOME10": Decimal("10.0")
        }
        return coupon_discounts.get(coupon_code, Decimal("0.0"))
    


    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        order = await Order.filter(id=order_id).prefetch_related("cart", "shipping_address").first()
        return order

    async def get_user_orders(
        self, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 10
    ) -> Tuple[List[Order], int]:
        """Get all orders for a user with pagination"""
        orders = await Order.filter(user=user_id).prefetch_related(
            "carts", "shipping_address"
        ).offset(skip).limit(limit).all()
        
        total = await Order.filter(user=user_id).count()
        return orders, total

    async def update_order(
        self, 
        order_id: str, 
        update_data: OrderUpdateSchema
    ) -> Optional[Order]:
        """Update order details"""
        order = await Order.filter(order_id=order_id).first()
        if not order:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        
        if update_dict:
            for key, value in update_dict.items():
                setattr(order, key, value)
            
            await order.save()
            await order.fetch_related("carts", "shipping_address", "delivery_option", "payment_method")
        
        return order

    async def cancel_order(self, order_id: str) -> Optional[Order]:
        """Cancel an order"""
        order = await self.get_order(order_id)
        if not order:
            return None
        
        # Only allow cancellation for certain statuses
        cancellable_statuses = [
            OrderStatus.PENDING.value, 
            OrderStatus.PROCESSING.value, 
            OrderStatus.CONFIRMED.value
        ]
        
        if order.status not in cancellable_statuses:
            raise ValueError(
                f"Cannot cancel order with status: {order.status}"
            )
        
        order.status = OrderStatus.CANCELLED
        await order.save()
        return order

    async def get_orders_by_status(
        self, 
        status: str, 
        skip: int = 0, 
        limit: int = 10
    ) -> Tuple[List[Order], int]:
        """Get orders by status with pagination"""
        orders = await Order.filter(status=status).prefetch_related(
            "carts", "shipping_address", "delivery_option", "payment_method"
        ).offset(skip).limit(limit).all()
        
        total = await Order.filter(status=status).count()
        return orders, total

    async def track_order(self, tracking_number: str) -> Optional[Order]:
        """Track order by tracking number"""
        order = await Order.filter(tracking_number=tracking_number).prefetch_related(
            "carts", "shipping_address", "delivery_option", "payment_method"
        ).first()
        return order