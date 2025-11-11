from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
from applications.user.models import *
from applications.user.schemas import *
from applications.user.customer import *
from decimal import Decimal, InvalidOperation
import uuid


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
    def _apply_coupon(subtotal: float, coupon_code: Optional[str]) -> float:
        """Apply coupon discount"""
        coupon_discounts = {
            "NEWUSER50": 50.0,
            "SAVE20": 20.0,
            "WELCOME10": 10.0
        }
        return coupon_discounts.get(coupon_code, 0.0)

    async def create_order(self, order_data: OrderCreateSchema) -> Order:
        """Create a new order"""
        # Calculate prices
        subtotal = 0
        for item in order_data.items:
            try:
                price = Decimal(item.price)  # will fail if item.price is not numeric
                subtotal += price * item.quantity
            except (InvalidOperation, ValueError, TypeError):
                # Handle invalid price
                print(f"Warning: invalid price '{item.price}' for item {item}")
                # Option 1: skip this item
                continue
                # Option 2: raise an error
                # raise ValueError(f"Invalid price '{item.price}' for item {item}")
        delivery_fee = order_data.delivery_option.price
        discount = self._apply_coupon(subtotal, order_data.coupon_code)
        total = subtotal + delivery_fee - discount

        # Create or get shipping address
        shipping_address, _ = await CustomerShippingAddress.get_or_create(
            id=order_data.shipping_address.id,
            defaults={
                "full_name": order_data.shipping_address.full_name,
                "address_line1": order_data.shipping_address.address_line,
                "address_line2": order_data.shipping_address.address_line2,
                "city": order_data.shipping_address.city,
                "state": order_data.shipping_address.state,
                "postal_code": order_data.shipping_address.postal_code,
                "country": order_data.shipping_address.country,
                "phone_number": order_data.shipping_address.phone_number,
                "is_default": order_data.shipping_address.is_default,
            }
        )

        # Create delivery option
        delivery_option = await DeliveryType.create(
            type=order_data.delivery_option.type,
            title=order_data.delivery_option.title,
            description=order_data.delivery_option.description,
            price=Decimal(str(order_data.delivery_option.price))
        )

        # Create payment method
        payment_method = await PaymentMethodType.create(
            type=order_data.payment_method.type,
            name=order_data.payment_method.name
        )

        # Create order
        order = await Order.create(
            order_id=self._generate_order_id(),
            user_id=order_data.user_id,
            shipping_address=shipping_address,
            delivery_option=delivery_option,
            payment_method=payment_method,
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
        for item_data in order_data.items:
            await OrderItem.create(
                order=order,
                item_id=item_data.item_id,
                title=item_data.title,
                price=Decimal(item_data.price),
                quantity=item_data.quantity,
                image_path=item_data.image_path
            )

        # Fetch order with related data
        await order.fetch_related("items", "shipping_address", "delivery_option", "payment_method")
        return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        order = await Order.filter(order_id=order_id).prefetch_related(
            "items", "shipping_address", "delivery_option", "payment_method"
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
            "items", "shipping_address", "delivery_option", "payment_method"
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
            await order.fetch_related("items", "shipping_address", "delivery_option", "payment_method")
        
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
            "items", "shipping_address", "delivery_option", "payment_method"
        ).offset(skip).limit(limit).all()
        
        total = await Order.filter(status=status).count()
        return orders, total

    async def track_order(self, tracking_number: str) -> Optional[Order]:
        """Track order by tracking number"""
        order = await Order.filter(tracking_number=tracking_number).prefetch_related(
            "items", "shipping_address", "delivery_option", "payment_method"
        ).first()
        return order