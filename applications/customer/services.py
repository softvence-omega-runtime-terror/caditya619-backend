from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from applications.user.models import *
from applications.user.customer import *
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from app.token import get_current_user
from decimal import Decimal, InvalidOperation
import uuid
import time
from fastapi import Depends
from tortoise.models import Model

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