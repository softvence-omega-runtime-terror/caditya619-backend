from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from applications.user.models import User
from applications.user.customer import CustomerShippingAddress
from applications.customer.models import Order, SubOrder, SubOrderItem, OrderStatus
from applications.customer.schemas import OrderCreateSchema, OrderUpdateSchema
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



# ============================================================
# SERVICE - applications.customer.services.py
# ============================================================

class OrderService:
    
    @staticmethod
    def _generate_order_id() -> str:
        return f"ORD_{uuid.uuid4().hex[:8].upper()}"
    
    @staticmethod
    def _generate_tracking_number() -> str:
        import random
        return f"TRK{random.randint(100000000, 999999999)}"
    
    async def create_order_with_sub_orders(
        self, 
        order_data: OrderCreateSchema, 
        current_user
    ) -> Order:
        """
        Create parent order with multiple sub-orders (one per vendor)
        """
        
        user_id = current_user.id
        
        # Step 1: Group items by vendor
        vendor_groups = await self._group_items_by_vendor(order_data.items)
        
        if not vendor_groups:
            raise ValueError("No valid items to order")
        
        # Step 2: Calculate totals
        grand_subtotal = Decimal("0")
        grand_delivery_fee = Decimal("0")
        
        for vendor_id, items in vendor_groups.items():
            for item_data in items:
                grand_subtotal += item_data['price'] * item_data['quantity']
            grand_delivery_fee += Decimal(str(order_data.delivery_option.price))
        
        # Apply discount
        discount = self._apply_coupon(grand_subtotal, order_data.coupon_code)
        grand_total = grand_subtotal + grand_delivery_fee - discount
        
        # Step 3: Create parent order
        order_id = self._generate_order_id()
        
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
        
        parent_order = await Order.create(
            id=order_id,
            user_id=user_id,
            shipping_address=shipping_data,
            subtotal=grand_subtotal,
            delivery_fee=grand_delivery_fee,
            total=grand_total,
            coupon_code=order_data.coupon_code,
            discount=discount,
            payment_method=order_data.payment_method.type,
            payment_status="unpaid",
            metadata={
                "payment_method": {
                    "type": order_data.payment_method.type,
                    "name": getattr(order_data.payment_method, 'name', '')
                }
            }
        )
        
        # Step 4: Create sub-orders for each vendor
        for vendor_id, items in vendor_groups.items():
            await self._create_sub_order(
                parent_order=parent_order,
                vendor_id=vendor_id,
                items=items,
                delivery_option=order_data.delivery_option,
                shipping_data=shipping_data
            )
        
        # Fetch related data
        await parent_order.fetch_related("sub_orders__items__item", "sub_orders__vendor")
        
        return parent_order
    
    async def _group_items_by_vendor(self, items_input) -> Dict[int, List]:
        """Group order items by vendor"""
        from applications.items.models import Item
        
        vendor_groups = {}
        
        for item_input in items_input:
            item = await Item.get(id=item_input.item_id).prefetch_related('vendor__vendor_profile')
            
            # # Validate item
            # if item.status != ItemStatus.ACTIVE:
            #     raise ValueError(f"Item '{item.title}' is not available")
            
            if item.stock < item_input.quantity:
                raise ValueError(f"Insufficient stock for '{item.title}'")
            
            # Validate vendor
            if not item.vendor or not item.vendor.is_vendor or not item.vendor.is_active:
                raise ValueError(f"Vendor for '{item.title}' is not available")
            
            # Group by vendor
            vendor_id = item.vendor_id
            if vendor_id not in vendor_groups:
                vendor_groups[vendor_id] = []
            
            vendor_groups[vendor_id].append({
                'item': item,
                'title': item.title,
                'price': Decimal(str(item.price)),
                'quantity': item_input.quantity,
                'image_path': getattr(item, 'image', '')
            })
        
        return vendor_groups
    
    async def _create_sub_order(
        self,
        parent_order: Order,
        vendor_id: int,
        items: List,
        delivery_option,
        shipping_data: dict
    ):
        """Create a sub-order for one vendor"""
        from applications.user.vendor import VendorProfile
        from applications.user.models import User
        
        # Calculate sub-order totals
        subtotal = sum(item['price'] * item['quantity'] for item in items)
        delivery_fee = Decimal(str(delivery_option.price))
        total = subtotal + delivery_fee
        
        # Get vendor info
        vendor = await User.get(id=vendor_id).prefetch_related('vendor_profile')
        vendor_profile = await VendorProfile.get_or_none(user=vendor)
        
        vendor_info = {
            "vendor_id": vendor_id,
            "vendor_name": vendor.name,
            "vendor_email": vendor.email or None,
            "vendor_phone": vendor.phone,
            "is_vendor": vendor.is_vendor,
            "is_active": vendor.is_active
        }
        
        if vendor_profile:
            vendor_info.update({
                "store_name": vendor_profile.owner_name,
                "store_type": vendor_profile.type,
                "store_latitude": vendor_profile.latitude,
                "store_longitude": vendor_profile.longitude,
                "profile_is_active": vendor_profile.is_active
            })
        
        delivery_option_data = {
            "type": delivery_option.type,
            "title": getattr(delivery_option, 'title', ''),
            "description": getattr(delivery_option, 'description', ''),
            "price": float(delivery_option.price)
        }
        
        # Create sub-order
        sub_order = await SubOrder.create(
            parent_order=parent_order,
            vendor_id=vendor_id,
            vendor_info=vendor_info,
            delivery_type=delivery_option.type,
            delivery_option=delivery_option_data,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            status=OrderStatus.PENDING,
            tracking_number=self._generate_tracking_number(),
            estimated_delivery=self._calculate_estimated_delivery(delivery_option.type)
        )
        
        # Create sub-order items and update stock
        for item_data in items:
            await SubOrderItem.create(
                sub_order=sub_order,
                item=item_data['item'],
                title=item_data['title'],
                price=str(item_data['price']),
                quantity=item_data['quantity'],
                image_path=item_data['image_path']
            )
            
            # # Decrease stock
            # item_data['item'].stock -= item_data['quantity']
            # item_data['item'].total_sale += item_data['quantity']
            
            # if item_data['item'].stock == 0:
            #     from applications.items.models import ItemStatus
            #     item_data['item'].status = ItemStatus.OUT_OF_STOCK
            
            await item_data['item'].save(update_fields=['stock', 'total_sale'])
        
        return sub_order
    
    def _calculate_estimated_delivery(self, delivery_type: str) -> datetime:
        """Calculate estimated delivery time"""
        minutes_map = {
            "combined": 60,  # 60 minutes
            "split": 30,   # 30 minutes
            "urgent": 15     # 15 minutes
        }
        minutes = minutes_map.get(delivery_type, 60)
        return datetime.utcnow() + timedelta(minutes=minutes)
    
    @staticmethod
    def _apply_coupon(subtotal: Decimal, coupon_code: Optional[str]) -> Decimal:
        coupon_discounts = {
            "NEWUSER50": Decimal("50.0"),
            "SAVE20": Decimal("20.0"),
            "WELCOME10": Decimal("10.0")
        }
        return coupon_discounts.get(coupon_code, Decimal("0.0"))
    
    async def update_order_with_sub_orders(
        self,
        order_id: str,
        order_data: OrderUpdateSchema,
        current_user
    ) -> Order:
        """
        Update an existing order with granular sub-order modifications.
        
        Capabilities:
          - Add/remove/modify items within a sub-order
          - Change delivery_option and payment_method per sub-order
          - Cancel individual sub-orders (removes from order)
          - Add new sub-orders
          - Update shipping_address
          - Delete entire order if all sub-orders removed
          
        Only sends fields you wish to update - others remain unchanged.
        """
        
        # Fetch order and verify ownership
        order = await Order.get_or_none(id=order_id, user_id=current_user.id)
        if not order:
            raise ValueError("Order not found")
        
        # Validation: payment_status must be "unpaid"
        if order.payment_status != "unpaid":
            raise ValueError(f"Cannot update order with payment_status: {order.payment_status}")
        
        # Fetch sub-orders
        await order.fetch_related("sub_orders")
        existing_subs = order.sub_orders or []
        
        if not existing_subs:
            raise ValueError("Order has no sub-orders")
        
        # Validation: all sub-orders must have tracking_status == "pending"
        for sub_order in existing_subs:
            tracking_status = getattr(sub_order, "tracking_number_status", None) or getattr(sub_order, "tracking_status", None) or "pending"
            if tracking_status != "pending":
                raise ValueError(f"Cannot update. Sub-order {sub_order.tracking_number} status is '{tracking_status}', not 'pending'")
        
        # Update shipping address if provided (partial update)
        if order_data.shipping_address is not None:
            order.shipping_address = {
                "full_name": order_data.shipping_address.full_name or (order.shipping_address.get("full_name") if order.shipping_address else ""),
                "address_line1": order_data.shipping_address.address_line1 or (order.shipping_address.get("address_line1") if order.shipping_address else ""),
                "address_line2": order_data.shipping_address.address_line2 or (order.shipping_address.get("address_line2") if order.shipping_address else ""),
                "city": order_data.shipping_address.city or (order.shipping_address.get("city") if order.shipping_address else ""),
                "state": order_data.shipping_address.state or (order.shipping_address.get("state") if order.shipping_address else ""),
                "postal_code": order_data.shipping_address.postal_code or (order.shipping_address.get("postal_code") if order.shipping_address else ""),
                "country": order_data.shipping_address.country or (order.shipping_address.get("country") if order.shipping_address else ""),
                "phone_number": order_data.shipping_address.phone_number or (order.shipping_address.get("phone_number") if order.shipping_address else "")
            }
        
        # Update notes and metadata (only if provided)
        if order_data.notes is not None:
            order.notes = order_data.notes
        
        if order_data.metadata is not None:
            if order.metadata is None:
                order.metadata = {}
            order.metadata.update(order_data.metadata)
        
        # Track changes
        updated_sub_orders = []
        removed_sub_orders = []
        added_sub_orders = []
        
        # Process sub-order updates (only if provided)
        if order_data.sub_orders is not None:
            for sub_update in order_data.sub_orders:
                # Find matching sub-order by tracking_number
                matching_sub = None
                for sub in existing_subs:
                    if sub.tracking_number == sub_update.tracking_number:
                        matching_sub = sub
                        break
                
                # Handle cancellation (removes sub-order)
                if sub_update.status and sub_update.status.lower() == "cancelled":
                    if matching_sub:
                        # Hard delete the sub-order
                        await matching_sub.delete()
                        removed_sub_orders.append(sub_update.tracking_number)
                        existing_subs.remove(matching_sub)
                    continue
                
                if matching_sub:
                    # Update items if provided
                    if sub_update.items is not None:
                        await matching_sub.fetch_related("items")
                        
                        # Delete existing items and recreate
                        existing_items = matching_sub.items or []
                        for item in existing_items:
                            await item.delete()
                        
                        # Create new items
                        from applications.items.models import Item
                        new_items_count = 0
                        for item_data in sub_update.items:
                            item = await Item.get_or_none(id=item_data.item_id)
                            if item:
                                await SubOrderItem.create(
                                    sub_order=matching_sub,
                                    item=item,
                                    title=item_data.title,
                                    price=str(item_data.price),
                                    quantity=item_data.quantity,
                                    image_path=item_data.image_path
                                )
                                new_items_count += 1
                        
                        # Recalculate sub-order subtotal
                        subtotal = sum(
                            Decimal(str(item_data.price)) * item_data.quantity
                            for item_data in sub_update.items
                        )
                        matching_sub.subtotal = subtotal
                    
                    # Update delivery option if provided
                    if sub_update.delivery_option is not None:
                        matching_sub.delivery_type = sub_update.delivery_option.type
                        matching_sub.delivery_option = {
                            "type": sub_update.delivery_option.type,
                            "title": getattr(sub_update.delivery_option, 'title', ''),
                            "description": getattr(sub_update.delivery_option, 'description', ''),
                            "price": float(sub_update.delivery_option.price)
                        }
                        matching_sub.delivery_fee = Decimal(str(sub_update.delivery_option.price))
                    
                    # Update payment method if provided
                    if sub_update.payment_method is not None:
                        matching_sub.payment_method = {
                            "type": sub_update.payment_method.type,
                            "name": getattr(sub_update.payment_method, 'name', '')
                        }
                    
                    # Recalculate total
                    matching_sub.total = matching_sub.subtotal + matching_sub.delivery_fee
                    await matching_sub.save()
                    
                    updated_sub_orders.append({
                        "tracking_number": matching_sub.tracking_number,
                        "subtotal": float(matching_sub.subtotal),
                        "total": float(matching_sub.total)
                    })
                else:
                    # New sub-order to add
                    try:
                        # Get vendor info
                        from applications.user.models import User
                        from applications.user.vendor import VendorProfile
                        
                        vendor_id = None
                        if sub_update.items and len(sub_update.items) > 0:
                            from applications.items.models import Item
                            first_item = await Item.get_or_none(id=sub_update.items[0].item_id)
                            if first_item:
                                vendor_id = first_item.vendor_id
                        
                        if not vendor_id:
                            continue
                        
                        vendor = await User.get(id=vendor_id).prefetch_related('vendor_profile')
                        vendor_profile = await VendorProfile.get_or_none(user=vendor)
                        
                        vendor_info = {
                            "vendor_id": vendor_id,
                            "vendor_name": vendor.name,
                            "vendor_email": vendor.email or None,
                            "vendor_phone": vendor.phone,
                            "is_vendor": vendor.is_vendor,
                            "is_active": vendor.is_active
                        }
                        
                        if vendor_profile:
                            vendor_info.update({
                                "store_name": vendor_profile.owner_name,
                                "store_type": vendor_profile.type,
                                "store_latitude": vendor_profile.latitude,
                                "store_longitude": vendor_profile.longitude,
                                "profile_is_active": vendor_profile.is_active
                            })
                        
                        # Calculate subtotal for new items
                        subtotal = sum(
                            Decimal(str(item.price)) * item.quantity
                            for item in sub_update.items
                        )
                        
                        delivery_fee = Decimal(str(sub_update.delivery_option.price)) if sub_update.delivery_option else Decimal("0")
                        total = subtotal + delivery_fee
                        
                        # Generate unique tracking number
                        vendor_counts = {}
                        for sub in existing_subs:
                            vid = getattr(sub, "vendor_id", None)
                            if vid:
                                vendor_counts[vid] = vendor_counts.get(vid, 0) + 1
                        vendor_counts[vendor_id] = vendor_counts.get(vendor_id, 0) + 1
                        new_tracking = f"{vendor_id}-{str(order.id)[:8].upper()}-{vendor_counts[vendor_id]}"
                        
                        # Create sub-order
                        new_sub = await SubOrder.create(
                            parent_order=order,
                            vendor_id=vendor_id,
                            vendor_info=vendor_info,
                            delivery_type=sub_update.delivery_option.type if sub_update.delivery_option else "combined",
                            delivery_option=sub_update.delivery_option.dict() if sub_update.delivery_option else {},
                            subtotal=subtotal,
                            delivery_fee=delivery_fee,
                            total=total,
                            status=OrderStatus.PENDING,
                            tracking_number=new_tracking,
                            estimated_delivery=self._calculate_estimated_delivery(sub_update.delivery_option.type if sub_update.delivery_option else "combined")
                        )
                        
                        # Create items
                        from applications.items.models import Item
                        for item_data in sub_update.items:
                            item = await Item.get_or_none(id=item_data.item_id)
                            if item:
                                await SubOrderItem.create(
                                    sub_order=new_sub,
                                    item=item,
                                    title=item_data.title,
                                    price=str(item_data.price),
                                    quantity=item_data.quantity,
                                    image_path=item_data.image_path
                                )
                        
                        existing_subs.append(new_sub)
                        added_sub_orders.append(new_tracking)
                        
                    except Exception as e:
                        print(f"[UPDATE] Failed to add new sub-order: {e}")
        
        # Check if all sub-orders are removed
        if not existing_subs or len(existing_subs) == 0:
            # Delete the entire parent order
            await order.delete()
            return None
        
        # Recalculate order totals
        new_subtotal = Decimal("0")
        new_delivery_fee = Decimal("0")
        
        for sub in existing_subs:
            new_subtotal += Decimal(str(getattr(sub, "subtotal", 0) or 0))
            new_delivery_fee += Decimal(str(getattr(sub, "delivery_fee", 0) or 0))
        
        order.subtotal = float(new_subtotal)
        order.delivery_fee = float(new_delivery_fee)
        order.total = float(new_subtotal + new_delivery_fee - Decimal(str(order.discount or 0)))
        order.updated_at = datetime.utcnow()
        
        await order.save()
        
        return order



