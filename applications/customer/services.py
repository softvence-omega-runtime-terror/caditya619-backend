from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
from applications.user.models import *
from applications.user.schemas import *
from applications.user.customer import CustomerShippingAddress
from decimal import Decimal, InvalidOperation
import uuid
from applications.customer.models import DeliveryTypeEnum, DeliveryOption
import time
from fastapi import Depends
from tortoise.models import Model

class OrderService:
    
    @staticmethod
    def _generate_order_id() -> str:
        """Generate unique order ID"""
        return f"ORD_{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _generate_tracking_number() -> str:
        """Generate tracking number"""
        return f"TRK_{uuid.uuid4().hex[:10].upper()}"

    @staticmethod
    def _calculate_estimated_delivery(delivery_type: str) -> datetime:
        """Calculate estimated delivery date based on delivery type"""
        days_map = {
            "standard": 5,
            "express": 2,
            "pickup": 1
        }
        days = days_map.get(delivery_type, 5)
        return datetime.utcnow() + timedelta(days=days)

    @staticmethod
    def _apply_coupon(subtotal: Decimal, coupon_code: Optional[str]) -> Decimal:
        coupon_discounts = {
            "NEWUSER50": Decimal("50.0"),
            "SAVE20": Decimal("20.0"),
            "WELCOME10": Decimal("10.0")
    }
        return coupon_discounts.get(coupon_code, Decimal("0.0"))

    async def create_order(self, order_data: OrderCreateSchema, current_user) -> Order:
        """Create a new order"""
        # Calculate prices
        subtotal = Decimal("0")
        order_items = []
        shipping_address_id = order_data.shipping_address.id
    # Loop through each cart
        for cart_data in order_data.carts:
            # Fetch the cart with its items
            cart = await Cart.get(id=cart_data.cart_id).prefetch_related('items')
            
            # Calculate subtotal from cart items
            for cart_item in cart.items:
                try:
                    # Fetch the actual item to get price
                    item = await Item.get(id=cart_item.item_id)
                    price = Decimal(str(item.price))
                    quantity = cart_item.quantity
                    
                    subtotal += price * quantity
                    
                    # Store item details for order creation
                    order_items.append({
                        'item_id': str(item.id),
                        'title': item.title,
                        'price': price,
                        'quantity': quantity,
                        'image_path': item.image_path if hasattr(item, 'image_path') else ''
                    })
                    
                except (InvalidOperation, ValueError, TypeError, AttributeError) as e:
                    print(f"Warning: Error processing cart item {cart_item.id}: {e}")
                    continue
                except Exception as e:
                    print(f"Error fetching item {cart_item.item_id}: {e}")
                    continue
    
        # Get delivery fee as Decimal
        delivery_fee = Decimal(str(order_data.delivery_option.price))
        
        # Get discount as Decimal
        discount = self._apply_coupon(subtotal, order_data.coupon_code)
        
        # Calculate total
        total = subtotal + delivery_fee - discount
        user = current_user
        user_id = user.id
        print("user_id=======dfsdfsdfsdfds========:", user_id)

        # Create or get shipping address
        if not shipping_address_id:
            shipping_address_id = f"addr_{int(time.time() * 1000)}"
            # Create a new address
            shipping_address = await CustomerShippingAddress.create(
                id=shipping_address_id,
                user_id=user_id,
                full_name=order_data.shipping_address.full_name or "",
                address_line1=order_data.shipping_address.address_line1 or "",
                address_line2=order_data.shipping_address.address_line2 or "",
                city=order_data.shipping_address.city or "",
                state=order_data.shipping_address.state or "",
                country=order_data.shipping_address.country or "",
                phone_number=order_data.shipping_address.phone_number or "",
                is_default=order_data.shipping_address.is_default or False
            )
        else:
            # Fetch existing address
            shipping_address = await CustomerShippingAddress.get(id=shipping_address_id)

        # Create delivery option
        delivery_option = await DeliveryOption.create(
        type=order_data.delivery_option.type,  # Should be a DeliveryTypeEnum value
        title=order_data.delivery_option.title,
        description=order_data.delivery_option.description,
        price=Decimal(str(order_data.delivery_option.price))
)

        # Create or get payment method
        payment_method = await PaymentMethod.create(
        type=order_data.payment_method.type,  # PaymentMethodType value
        title=order_data.payment_method.title,
        description=order_data.payment_method.description,
        is_active=True
)

        # # Or get existing payment method
        # payment_method = await PaymentMethod.get(type=PaymentMethodType.COD)

        # Create order
        order = await Order.create(
            order_id=self._generate_order_id(),
            user_id=user_id,
            shipping_address=shipping_address,
            delivery_option=delivery_option,
            payment_method=order_data.payment_method.type,
            subtotal=Decimal(str(subtotal)),
            delivery_fee=Decimal(str(delivery_fee)),
            total=Decimal(str(total)),
            coupon_code=order_data.coupon_code,
            discount=Decimal(str(discount)),
            status=OrderStatus.PENDING,
            tracking_number=self._generate_tracking_number(),
            estimated_delivery=self._calculate_estimated_delivery(
                order_data.delivery_option.type
            ),
            metadata={"created_at": datetime.utcnow().isoformat()}
        )

        # Create order items
        for cart_data in order_data.carts:
            # Fetch the cart with its items
            cart = await Cart.get(id=cart_data.cart_id).prefetch_related("items__item")
            order_items = []
            for cart_item in cart.items:
                await OrderItem.create(
                    order=order,
                    item_id=cart_item.item,
                    title=cart_item.item.title,
                    price=Decimal(cart_item.item.price),
                    quantity=cart_item.quantity,
                    image_path=cart_item.item.image
                )

        # Fetch order with related data
        await order.fetch_related("carts", "shipping_address", "delivery_option", "payment_method")
        return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        order = await Order.filter(order_id=order_id).prefetch_related(
            "carts", "shipping_address", "delivery_option", "payment_method"
        ).first()
        return order

    async def get_user_orders(
        self, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 10
    ) -> Tuple[List[Order], int]:
        """Get all orders for a user with pagination"""
        orders = await Order.filter(user_id=user_id).prefetch_related(
            "carts", "shipping_address", "delivery_option", "payment_method"
        ).offset(skip).limit(limit).all()
        
        total = await Order.filter(user_id=user_id).count()
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