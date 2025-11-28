from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from applications.user.models import User
from applications.user.customer import CustomerShippingAddress
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
        subtotal = Decimal("0")
        order_items = []
        
        user = current_user
        user_id = user.id
        
        # Process items directly from order request
        for item_input in order_data.items:
            try:
                # Fetch the item from database
                item = await Item.get(id=item_input.item_id)
                
                # Check stock availability
                if item.stock < item_input.quantity:
                    raise ValueError(f"Insufficient stock for item: {item.title}")
                
                price = Decimal(str(item.price))
                quantity = item_input.quantity
                subtotal += price * quantity
                
                order_items.append({
                    'item': item,
                    'title': item.title,
                    'price': price,
                    'quantity': quantity,
                    'image_path': getattr(item, 'image', '')
                })
                
            except Item.DoesNotExist:
                raise ValueError(f"Item with id {item_input.item_id} not found")
            except Exception as e:
                print(f"Error processing item {item_input.item_id}: {e}")
                raise
        
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
        
        # Create order
        order_id = f"order_{int(time.time() * 1000)}"
        
        # Store delivery and payment details in metadata
        order_metadata = {
            "created_at": datetime.utcnow().isoformat(),
            "delivery_option": {
                "type": order_data.delivery_option.type,
                "title": getattr(order_data.delivery_option, 'title', ''),
                "description": getattr(order_data.delivery_option, 'description', ''),
                "price": float(order_data.delivery_option.price)
            },
            "payment_method": {
                "type": order_data.payment_method.type,
                "name": getattr(order_data.payment_method, 'name', '')
            }
        }
        
        order = await Order.create(
            id=order_id,  
            user_id=user_id,
            shipping_address_id=shipping_address.id,
            delivery_type=order_data.delivery_option.type, 
            payment_method=order_data.payment_method.type, 
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
            metadata=order_metadata
        )
        
        # Create order items
        for item_data in order_items:
            await OrderItem.create(
                order_id=order.id,
                item_id=item_data['item'].id,
                title=item_data['title'],
                price=str(item_data['price']),  
                quantity=item_data['quantity'],
                image_path=item_data['image_path']
            )
            
            # Update item stock
            item_data['item'].stock -= item_data['quantity']
            item_data['item'].total_sale += item_data['quantity']
            await item_data['item'].save(update_fields=['stock', 'total_sale'])
        
        # Fetch related data
        await order.fetch_related("shipping_address", "user", "items__item")
        return order


    def _generate_tracking_number(self) -> str:
        import random
        return f"TRK{random.randint(100000000, 999999999)}"


    def _calculate_estimated_delivery(self, delivery_type: str) -> datetime:
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
        coupon_discounts = {
            "NEWUSER50": Decimal("50.0"),
            "SAVE20": Decimal("20.0"),
            "WELCOME10": Decimal("10.0")
        }
        return coupon_discounts.get(coupon_code, Decimal("0.0"))


    # ============= SERVICE METHODS FOR UPDATE & CANCEL =============
    async def update_order(self, order_id: str, update_data: OrderUpdateSchema, current_user) -> dict:
        """Update order - only if status is PENDING"""
        try:
            order = await Order.get(id=order_id, user_id=current_user.id).prefetch_related(
                "items__item", "shipping_address", "user"
            )
            
            # Check if order is in PENDING status
            current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
            if current_status.lower() != "pending":
                raise ValueError(f"Cannot update order. Order status is '{current_status}'. Only 'pending' orders can be updated.")
            
            # Update fields if provided
            if update_data.status is not None:
                order.status = update_data.status
            if update_data.tracking_number is not None:
                order.tracking_number = update_data.tracking_number
            if update_data.transaction_id is not None:
                order.transaction_id = update_data.transaction_id
            if update_data.estimated_delivery is not None:
                order.estimated_delivery = update_data.estimated_delivery
            
            await order.save()
            await order.fetch_related("items__item", "shipping_address", "user")
            
            return self._format_order_response(order)
            
        except Order.DoesNotExist:
            raise ValueError(f"Order with id {order_id} not found")


    async def cancel_order(self, order_id: str, current_user) -> dict:
        """Cancel order - only if status is PENDING"""
        try:
            order = await Order.get(id=order_id, user_id=current_user.id).prefetch_related(
                "items__item", "shipping_address", "user"
            )
            
            # Check if order is in PENDING status
            current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
            if current_status.lower() != "pending":
                raise ValueError(f"Cannot cancel order. Order status is '{current_status}'. Only 'pending' orders can be cancelled.")
            
            # Update status to cancelled
            order.status = OrderStatus.CANCELLED
            await order.save()
            
            # Restore stock for all items in the order
            await order.fetch_related("items__item")
            for order_item in order.items:
                item = order_item.item
                item.stock += order_item.quantity
                item.total_sale -= order_item.quantity
                await item.save(update_fields=['stock', 'total_sale'])
            
            await order.fetch_related("items__item", "shipping_address", "user")
            
            return self._format_order_response(order)
            
        except Order.DoesNotExist:
            raise ValueError(f"Order with id {order_id} not found")


    # ============= SERVICE METHODS FOR RETRIEVAL =============
    async def get_order_by_id(self, order_id: str, current_user) -> dict:
        """Get a single order by ID"""
        try:
            order = await Order.get(id=order_id, user_id=current_user.id).prefetch_related(
                "items__item", "shipping_address", "user"
            )
            return self._format_order_response(order)
        except Order.DoesNotExist:
            raise ValueError(f"Order with id {order_id} not found")


    async def get_all_orders(self, current_user, skip: int = 0, limit: int = 10) -> dict:
        """Get all orders for the current user"""
        orders = await Order.filter(user_id=current_user.id).prefetch_related(
            "items__item", "shipping_address", "user"
        ).offset(skip).limit(limit).order_by('-order_date')
        
        total_count = await Order.filter(user_id=current_user.id).count()
        
        formatted_orders = [self._format_order_response(order) for order in orders]
        
        return {
            "orders": formatted_orders,
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "page_size": limit
        }


    def _format_order_response(self, order) -> dict:
        """Format order object to match the required JSON structure"""
        # Extract delivery and payment info from metadata
        delivery_info = order.metadata.get('delivery_option', {}) if order.metadata else {}
        payment_info = order.metadata.get('payment_method', {}) if order.metadata else {}
        
        # Format order items
        items = []
        if hasattr(order, 'items'):
            for order_item in order.items:
                items.append({
                    "productId": str(order_item.item.id) if hasattr(order_item, 'item') else str(order_item.item_id),
                    "title": order_item.title,
                    "price": order_item.price,
                    "quantity": order_item.quantity,
                    "imagePath": order_item.image_path
                })
        
        # Format shipping address
        shipping_address = None
        if order.shipping_address:
            addr = order.shipping_address
            shipping_address = {
                "id": str(addr.id),
                "fullName": addr.full_name,
                "addressLine1": addr.address_line1,
                "addressLine2": addr.address_line2,
                "city": addr.city,
                "state": addr.state,
                "postalCode": addr.postal_code,
                "country": addr.country,
                "phoneNumber": addr.phone_number,
                "isDefault": addr.is_default
            }
        
        return {
            "orderId": order.id,
            "userId": str(order.user_id),
            "items": items,
            "shippingAddress": shipping_address,
            "deliveryOption": {
                "type": delivery_info.get('type', order.delivery_type.value if hasattr(order.delivery_type, 'value') else str(order.delivery_type)),
                "title": delivery_info.get('title', ''),
                "description": delivery_info.get('description', ''),
                "price": delivery_info.get('price', float(order.delivery_fee))
            },
            "paymentMethod": {
                "type": payment_info.get('type', order.payment_method.value if hasattr(order.payment_method, 'value') else str(order.payment_method)),
                "name": payment_info.get('name', '')
            },
            "subtotal": float(order.subtotal),
            "deliveryFee": float(order.delivery_fee),
            "total": float(order.total),
            "couponCode": order.coupon_code,
            "discount": float(order.discount),
            "orderDate": order.order_date.isoformat(),
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "transactionId": order.transaction_id,
            "trackingNumber": order.tracking_number,
            "estimatedDelivery": order.estimated_delivery.isoformat() if order.estimated_delivery else None,
            "metadata": order.metadata
        }
