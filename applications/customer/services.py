from typing import Dict, List, Optional, Tuple
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

from applications.user.vendor import VendorProfile
# from app.token import get_current_user
# current_user = Depends(get_current_user)

class ShippingAddressService:
    """Service layer for managing customer shipping addresses"""
    
    MAX_ADDRESSES_PER_TYPE = 20  # Only one address per type allowed
    MAX_TOTAL_ADDRESSES = 50  # Maximum 3 addresses total
    
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



# ============================================================
# SERVICE - applications.customer.services.py
# ============================================================

# applications.customer.services.py

class OrderService:
    @staticmethod
    def _generate_order_id() -> str:
        return f"ORD_{uuid.uuid4().hex[:8].upper()}"
    
    @staticmethod
    def _generate_parent_order_id() -> str:
        """Generate a parent order ID for grouping multiple vendor orders"""
        return f"PORD_{uuid.uuid4().hex[:8].upper()}"

    async def create_orders(
        self, 
        order_data: OrderCreateSchema, 
        current_user
    ) -> List[Order]:
        """
        Create multiple orders grouped by vendor from a single request.
        Returns a list of Order objects.
        """
        user = current_user
        user_id = user.id
        
        # Group items by vendor
        vendor_items_map: Dict[int, List[Dict]] = {}
        
        for item_input in order_data.items:
            try:
                item = await Item.get(id=item_input.item_id).prefetch_related(
                    'vendor__vendor_profile'
                )
                
                # Validate vendor
                if not item.vendor:
                    raise ValueError(f"Item '{item.title}' has no associated vendor")
                
                if not item.vendor.is_vendor:
                    raise ValueError(f"Item '{item.title}' vendor account is invalid")
                
                if not item.vendor.is_active:
                    raise ValueError(f"Vendor for item '{item.title}' is currently inactive")
                
                if item.stock < item_input.quantity:
                    raise ValueError(f"Insufficient stock for item: {item.title}")
                
                # Group by vendor
                vendor_id = item.vendor_id
                if vendor_id not in vendor_items_map:
                    vendor_items_map[vendor_id] = []
                
                price = Decimal(str(item.price))
                quantity = item_input.quantity
                
                vendor_items_map[vendor_id].append({
                    'item': item,
                    'title': item.title,
                    'price': price,
                    'quantity': quantity,
                    'image_path': getattr(item, 'image', ''),
                    'vendor': item.vendor
                })
                
            except DoesNotExist:
                raise ValueError(f"Item with id {item_input.item_id} not found")
            except Exception as e:
                print(f"Error processing item {item_input.item_id}: {e}")
                raise
        
        if not vendor_items_map:
            raise ValueError("No valid items in order")
        # Generate parent order ID for this group
        parent_order_id = self._generate_parent_order_id()

        # Create one order per vendor
        created_orders = []
        
        for vendor_id, items in vendor_items_map.items():
            # Calculate subtotal for this vendor
            subtotal = sum(item['price'] * item['quantity'] for item in items)
            
            # Apply delivery fee and discount
            delivery_fee = Decimal(str(order_data.delivery_option.price))
            discount = self._apply_coupon(subtotal, order_data.coupon_code)
            total = subtotal + delivery_fee - discount
            
            # Get vendor info
            first_item_vendor = items[0]['vendor']
            vendor_profile = await VendorProfile.get_or_none(user=first_item_vendor)
            
            vendor_info = {
                "vendor_id": vendor_id,
                "vendor_name": first_item_vendor.name,
                "vendor_phone": first_item_vendor.phone,
                "vendor_email": first_item_vendor.email or None,
                "is_vendor": first_item_vendor.is_vendor,
                "is_active": first_item_vendor.is_active
            }
            
            if vendor_profile:
                vendor_info.update({
                    "store_name": vendor_profile.owner_name,
                    "store_type": vendor_profile.type,
                    "store_latitude": vendor_profile.latitude,
                    "store_longitude": vendor_profile.longitude,
                    "kyc_status": vendor_profile.kyc_status,
                    "profile_is_active": vendor_profile.is_active
                })
            
            # Store shipping address in metadata
            shipping_data = {
                "full_name": order_data.shipping_address.full_name or "",
                "address_line1": order_data.shipping_address.address_line1 or "",
                "address_line2": order_data.shipping_address.address_line2 or "",
                "city": order_data.shipping_address.city or "",
                "state": order_data.shipping_address.state or "",
                "postal_code": order_data.shipping_address.postal_code or "",
                "country": order_data.shipping_address.country or "",
                "phone_number": order_data.shipping_address.phone_number or ""
            }
            
            order_metadata = {
                "shipping_address": shipping_data,
                "delivery_option": {
                    "type": order_data.delivery_option.type,
                    "title": getattr(order_data.delivery_option, 'title', ''),
                    "description": getattr(order_data.delivery_option, 'description', ''),
                    "price": float(order_data.delivery_option.price)
                },
                "payment_method": {
                    "type": order_data.payment_method.type,
                    "name": getattr(order_data.payment_method, 'name', '')
                },
                "vendor_info": vendor_info
            }
            
            order_status = OrderStatus.PROCESSING if order_data.payment_method.type != "cashfree" else OrderStatus.PENDING

            # Create order
            order_id = self._generate_order_id()
            order = await Order.create(
                id=order_id,
                parent_order_id=parent_order_id,
                user_id=user_id,
                vendor_id=vendor_id,
                shipping_address_id=None,
                delivery_type=order_data.delivery_option.type,
                payment_method=order_data.payment_method.type,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total=total,
                coupon_code=order_data.coupon_code,
                discount=discount,
                status=order_status,   
                payment_status="unpaid",
                tracking_number=self._generate_tracking_number(),
                estimated_delivery=self._calculate_estimated_delivery(
                    order_data.delivery_option.type
                ),
                metadata=order_metadata
            )
            
            # Create order items
            for item_data in items:
                await OrderItem.create(
                    order_id=order.id,
                    item_id=item_data['item'].id,
                    title=item_data['title'],
                    price=str(item_data['price']),
                    quantity=item_data['quantity'],
                    image_path=item_data['image_path']
                )
                
            
            await order.fetch_related("user", "items__item")
            created_orders.append(order)
        
        return created_orders

    def _generate_tracking_number(self) -> str:
        import random
        return f"TRK{random.randint(100000000, 999999999)}"

    def _calculate_estimated_delivery(self, delivery_type: str) -> datetime:
        days_map = {
            "combined": 5,
            "split": 2,
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
