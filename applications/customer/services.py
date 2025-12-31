from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from applications.user.models import User
from applications.user.customer import CustomerShippingAddress
from applications.items.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from decimal import Decimal
import uuid
import time
from tortoise.models import Model
from fastapi import Depends, HTTPException, status
from tortoise.exceptions import DoesNotExist
from applications.user.rider import RiderFeesAndBonuses
from applications.user.vendor import VendorProfile

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
            is_default=True,
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

# class OrderService:
#     @staticmethod
#     def _generate_order_id() -> str:
#         return f"ORD_{uuid.uuid4().hex[:8].upper()}"
    
#     @staticmethod
#     def _generate_parent_order_id() -> str:
#         """Generate a parent order ID for grouping multiple vendor orders"""
#         return f"PORD_{uuid.uuid4().hex[:8].upper()}"

#     async def create_orders(
#         self, 
#         order_data: OrderCreateSchema, 
#         current_user
#     ) -> List[Order]:
#         """
#         Create multiple orders grouped by vendor from a single request.
#         Returns a list of Order objects.
#         """
#         user = current_user
#         user_id = user.id
        
#         # Group items by vendor
#         vendor_items_map: Dict[int, List[Dict]] = {}
        
#         for item_input in order_data.items:
#             try:
#                 item = await Item.get(id=item_input.item_id).prefetch_related(
#                     'vendor__vendor_profile'
#                 )
                
#                 # Validate vendor
#                 if not item.vendor:
#                     raise ValueError(f"Item '{item.title}' has no associated vendor")
                
#                 if not item.vendor.is_vendor:
#                     raise ValueError(f"Item '{item.title}' vendor account is invalid")
                
#                 if not item.vendor.is_active:
#                     raise ValueError(f"Vendor for item '{item.title}' is currently inactive")
                
#                 if item.stock < item_input.quantity:
#                     raise ValueError(f"Insufficient stock for item: {item.title}")
                
#                 # Group by vendor
#                 vendor_id = item.vendor_id
#                 if vendor_id not in vendor_items_map:
#                     vendor_items_map[vendor_id] = []
                
#                 price = Decimal(str(item.price))
#                 quantity = item_input.quantity
                
#                 vendor_items_map[vendor_id].append({
#                     'item': item,
#                     'title': item.title,
#                     'price': item.sell_price,
#                     'quantity': quantity,
#                     'image_path': getattr(item, 'image', ''),
#                     'vendor': item.vendor
#                 })

#                 print(f"item.price = '{item.price}' (Qty: {item.discounted_price}) to item.sell_price = {item.sell_price} order group.")
                
#             except DoesNotExist:
#                 raise ValueError(f"Item with id {item_input.item_id} not found")
#             except Exception as e:
#                 print(f"Error processing item {item_input.item_id}: {e}")
#                 raise
        
#         if not vendor_items_map:
#             raise ValueError("No valid items in order")
#         # Generate parent order ID for this group
#         parent_order_id = self._generate_parent_order_id()

#         # Calculate grand total of all orders to apply coupon
#         grand_subtotal = Decimal("0")
#         for items in vendor_items_map.values():
#             grand_subtotal += sum(item['price'] * item['quantity'] for item in items)
#         print(f"grand_subtotal =========== {grand_subtotal}")

#          # Apply coupon only once on the grand total
#         total_coupon_discount = self._apply_coupon(grand_subtotal, order_data.coupon_code)
        
#         # Distribute discount proportionally across orders
#         vendor_count = len(vendor_items_map)
#         discount_per_order = total_coupon_discount / vendor_count if vendor_count > 0 else Decimal("0")
        

#         # Create one order per vendor
#         created_orders = []
        
#         for vendor_id, items in vendor_items_map.items():
#             # Calculate subtotal for this vendor
            
#             subtotal = sum(item['price'] * item['quantity'] for item in items)
#             print(f"subtotal =========== {subtotal}")
#             # Apply delivery fee and discount
#             # fees= await RiderFeesAndBonuses.filter().first()
#             # delivery_fee = fees.rider_delivery_fee
#             delivery_fee = Decimal(str(order_data.delivery_option.price))
#             print(f"delivery_fee =========== {delivery_fee}")

#             # coupon_discount = self._apply_coupon(subtotal, order_data.coupon_code)
#             total = subtotal + delivery_fee - discount_per_order
#             print(f"total =========== {total}")
            
#             # Get vendor info
#             first_item_vendor = items[0]['vendor']
#             vendor_profile = await VendorProfile.get_or_none(user=first_item_vendor)
            
#             vendor_info = {
#                 "vendor_id": vendor_id,
#                 "vendor_name": first_item_vendor.name,
#                 "vendor_phone": first_item_vendor.phone,
#                 "vendor_email": first_item_vendor.email or None,
#                 "is_vendor": first_item_vendor.is_vendor,
#                 "is_active": first_item_vendor.is_active
#             }
            
#             if vendor_profile:
#                 vendor_info.update({
#                     "store_name": vendor_profile.owner_name,
#                     "store_type": vendor_profile.type,
#                     "store_latitude": vendor_profile.latitude,
#                     "store_longitude": vendor_profile.longitude,
#                     "kyc_status": vendor_profile.kyc_status,
#                     "profile_is_active": vendor_profile.is_active
#                 })
            
#             # Store shipping address in metadata
#             shipping_data = {
#                 "full_name": order_data.shipping_address.full_name or "",
#                 "address_line1": order_data.shipping_address.address_line1 or "",
#                 "address_line2": order_data.shipping_address.address_line2 or "",
#                 "city": order_data.shipping_address.city or "",
#                 "state": order_data.shipping_address.state or "",
#                 "postal_code": order_data.shipping_address.postal_code or "",
#                 "country": order_data.shipping_address.country or "",
#                 "phone_number": order_data.shipping_address.phone_number or ""
#             }
            
#             order_metadata = {
#                 "shipping_address": shipping_data,
#                 "delivery_option": {
#                     "type": order_data.delivery_option.type,
#                     "title": getattr(order_data.delivery_option, 'title', ''),
#                     "description": getattr(order_data.delivery_option, 'description', ''),
#                     "price": float(order_data.delivery_option.price)
#                 },
#                 "payment_method": {
#                     "type": order_data.payment_method.type,
#                     "name": getattr(order_data.payment_method, 'name', '')
#                 },
#                 "vendor_info": vendor_info
#             }
            
#             order_status_update = OrderStatus.PROCESSING if order_data.payment_method.type != "cashfree" else OrderStatus.PENDING


#             # Create order with parent_order_id
#             order_id = self._generate_order_id()
#             order = await Order.create(
#                 id=order_id,
#                 parent_order_id=parent_order_id,
#                 user_id=user_id,
#                 vendor_id=vendor_id,
#                 shipping_address_id=None,
#                 delivery_type=order_data.delivery_option.type,
#                 payment_method=order_data.payment_method.type,
#                 subtotal=subtotal,
#                 delivery_fee=delivery_fee,
#                 total=total,
#                 coupon_code=order_data.coupon_code,
#                 discount=discount_per_order,
#                 status=order_status_update,   
#                 payment_status="unpaid",
#                 tracking_number=self._generate_tracking_number(),
#                 estimated_delivery=self._calculate_estimated_delivery(
#                     order_data.delivery_option.type
#                 ),
#                 metadata=order_metadata
#             )
            
#             # Create order items
#             for item_data in items:
#                 await OrderItem.create(
#                     order_id=order.id,
#                     item_id=item_data['item'].id,
#                     title=item_data['title'],
#                     price=str(item_data['price']),
#                     quantity=item_data['quantity'],
#                     image_path=item_data['image_path']
#                 )
                
            
#             await order.fetch_related("user", "items__item")
#             created_orders.append(order)
        
#         return created_orders

#     def _generate_tracking_number(self) -> str:
#         import random
#         return f"TRK{random.randint(100000000, 999999999)}"

#     def _calculate_estimated_delivery(self, delivery_type: str) -> datetime:
#         days_map = {
#             "combined": 5,
#             "split": 2,
#             "urgent": 1
#         }
#         days = days_map.get(delivery_type, 5)
#         return datetime.utcnow() + timedelta(days=days)

#     @staticmethod
#     def _apply_coupon(subtotal: Decimal, coupon_code: Optional[str]) -> Decimal:
#         coupon_discounts = {
#             "NEWUSER50": Decimal("50.0"),
#             "SAVE20": Decimal("20.0"),
#             "WELCOME10": Decimal("10.0")
#         }
#         return coupon_discounts.get(coupon_code, Decimal("0.0"))





class OrderService:
    """
    Enhanced OrderService supporting three order types:
    1. COMBINED: Single order for all items, vendor confirmation required
    2. SPLIT: One order per vendor, each vendor confirms independently
    3. URGENT: One order per urgent item vendor, auto-assign rider after confirmation
    """

    @staticmethod
    def _generate_order_id() -> str:
        return f"ORD_{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _generate_parent_order_id() -> str:
        """Generate a parent order ID for grouping multiple vendor orders"""
        return f"PORD_{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _generate_tracking_number() -> str:
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

    def _classify_items_by_urgency(self, vendor_items_map: Dict[int, List[Dict]]) -> Tuple[Dict, Dict]:
        """
        Separate items into urgent and non-urgent vendors.
        Urgent items: Medicine category items marked as OTC/emergency
        
        Returns:
            Tuple of (urgent_vendor_map, non_urgent_vendor_map)
        """
        urgent_vendors = {}
        non_urgent_vendors = {}
        
        for vendor_id, items in vendor_items_map.items():
            has_urgent = False
            
            for item_data in items:
                item = item_data['item']
                # Check if item is medicine category and marked urgent (isOTC flag)
                if hasattr(item, 'category') and item.category:
                    is_medicine = item.category.type == "medicine"
                    is_urgent = getattr(item, 'isOTC', False)
                    print(f"Item '{item.title}': is_medicine={is_medicine}, is_urgent={is_urgent}, isOTC={getattr(item, 'isOTC', None)}")
                    
                    if is_medicine and is_urgent:
                        has_urgent = True
                        break
            
            if has_urgent:
                print(f"Vendor {vendor_id} classified as URGENT")
                urgent_vendors[vendor_id] = items
            else:
                print(f"Vendor {vendor_id} classified as NON-URGENT")
                non_urgent_vendors[vendor_id] = items
        
        return urgent_vendors, non_urgent_vendors

    async def create_orders(
        self,
        order_data: OrderCreateSchema,
        current_user,
        order_type: str = "combined"
    ) -> List[Order]:
        """
        Create orders based on type: combined, split, or urgent.
        
        Args:
            order_data: Order creation schema with items and shipping info
            current_user: Current user making the order
            order_type: Type of order - "combined", "split", or "urgent"
        
        Returns:
            List of created Order objects
        """
        user = current_user
        user_id = user.id

        # Group items by vendor
        vendor_items_map: Dict[int, List[Dict]] = {}
        
        for item_input in order_data.items:
            try:
                item = await Item.get(id=item_input.item_id).prefetch_related(
                    'vendor__vendor_profile', 'category'
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

                vendor_id = item.vendor_id
                if vendor_id not in vendor_items_map:
                    vendor_items_map[vendor_id] = []

                vendor_items_map[vendor_id].append({
                    'item': item,
                    'title': item.title,
                    'price': item.sell_price,
                    'quantity': item_input.quantity,
                    'image_path': getattr(item, 'image', ''),
                    'vendor': item.vendor
                })

            except DoesNotExist:
                raise ValueError(f"Item with id {item_input.item_id} not found")
            except Exception as e:
                print(f"[ERROR] Error processing item {item_input.item_id}: {e}")
                raise

        if not vendor_items_map:
            raise ValueError("No valid items in order")

        # Determine order type based on items
        if order_type == "combined":
            # Check for urgent items in combined order
            urgent_vendors, non_urgent_vendors = self._classify_items_by_urgency(vendor_items_map)
            
            if urgent_vendors and non_urgent_vendors:
                # Mixed case: urgent + non-urgent
                print(f"[ORDER] Mixed order detected - {len(urgent_vendors)} urgent vendors, {len(non_urgent_vendors)} non-urgent")
                return await self._create_mixed_orders(
                    urgent_vendors, non_urgent_vendors, order_data, current_user
                )
            elif urgent_vendors:
                # All items are urgent
                print(f"[ORDER] All items urgent - creating urgent orders")
                return await self._create_urgent_orders(
                    urgent_vendors, order_data, current_user
                )
            else:
                # All items non-urgent - standard combined
                print(f"[ORDER] Standard combined order for {len(non_urgent_vendors)} vendors")
                return await self._create_combined_orders(
                    non_urgent_vendors, order_data, current_user
                )
        
        elif order_type == "split":
            print(f"[ORDER] Split order - one order per vendor ({len(vendor_items_map)} vendors)")
            created_orders = []
            urgent_vendors, non_urgent_vendors = self._classify_items_by_urgency(vendor_items_map)
            if urgent_vendors:
                urgent_orders = await self._create_urgent_orders(urgent_vendors, order_data, current_user)
                created_orders.extend(urgent_orders)
            if non_urgent_vendors:
                split_orders = await self._create_split_orders(non_urgent_vendors, order_data, current_user)
                created_orders.extend(split_orders)
            return created_orders
        
        elif order_type == "urgent":
            print(f"[ORDER] Urgent orders for {len(vendor_items_map)} vendors")
            return await self._create_urgent_orders(
                vendor_items_map, order_data, current_user
            )
        
        else:
            raise ValueError(f"Invalid order type: {order_type}")

    async def _create_combined_orders(
        self,
        vendor_items_map: Dict[int, List[Dict]],
        order_data: OrderCreateSchema,
        current_user
    ) -> List[Order]:
        """
        Create combined orders. One order per vendor group.
        Vendor must confirm before rider assignment.
        """
        created_orders = []
        parent_order_id = self._generate_parent_order_id()

        # Calculate grand total for coupon
        grand_subtotal = Decimal("0")
        for items in vendor_items_map.values():
            grand_subtotal += sum(item["price"] * item['quantity'] for item in items)

        total_coupon_discount = self._apply_coupon(grand_subtotal, order_data.coupon_code)
        vendor_count = len(vendor_items_map)
        discount_per_order = total_coupon_discount / vendor_count if vendor_count > 0 else Decimal("0")

        for vendor_id, items in vendor_items_map.items():
            try:
                # Calculate totals
                subtotal = sum(item["price"] * item['quantity'] for item in items)
                delivery_fee = Decimal(str(order_data.delivery_option.price))
                total = subtotal + delivery_fee - discount_per_order

                # Get vendor info
                first_item_vendor = items[0]['vendor']
                vendor_profile = await VendorProfile.get_or_none(user=first_item_vendor)
                
                vendor_info = self._build_vendor_info(first_item_vendor, vendor_profile)

                # Build metadata
                order_metadata = self._build_order_metadata(
                    order_data, vendor_info, "combined"
                )

                # Determine status
                order_status_update = (
                    OrderStatus.PROCESSING 
                    if order_data.payment_method.type != "cashfree" 
                    else OrderStatus.PENDING
                )

                # Create order
                order_id = self._generate_order_id()
                order = await Order.create(
                    id=order_id,
                    parent_order_id=parent_order_id,
                    user_id=current_user.id,
                    vendor_id=vendor_id,
                    shipping_address_id=None,
                    delivery_type=order_data.delivery_option.type,
                    payment_method=order_data.payment_method.type,
                    subtotal=subtotal,
                    delivery_fee=delivery_fee,
                    total=total,
                    coupon_code=order_data.coupon_code,
                    discount=discount_per_order,
                    status=order_status_update,
                    payment_status="unpaid",
                    tracking_number=self._generate_tracking_number(),
                    estimated_delivery=self._calculate_estimated_delivery(
                        order_data.delivery_option.type
                    ),
                    metadata=order_metadata,
                    is_combined=True
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
                print(f"[ORDER] Created combined order {order.id} for vendor {vendor_id}")

            except Exception as e:
                print(f"[ERROR] Failed to create combined order for vendor {vendor_id}: {e}")
                for created_order in created_orders:
                    await created_order.delete()
                raise

        return created_orders

    async def _create_split_orders(
        self,
        vendor_items_map: Dict[int, List[Dict]],
        order_data: OrderCreateSchema,
        current_user
    ) -> List[Order]:
        """
        Create split orders. One separate order per vendor.
        Each vendor must confirm independently.
        """
        created_orders = []
        parent_order_id = self._generate_parent_order_id()

        grand_subtotal = Decimal("0")
        for items in vendor_items_map.values():
            grand_subtotal += sum(item["price"] * item['quantity'] for item in items)

        total_coupon_discount = self._apply_coupon(grand_subtotal, order_data.coupon_code)
        vendor_count = len(vendor_items_map)
        discount_per_order = total_coupon_discount / vendor_count if vendor_count > 0 else Decimal("0")

        related_order_ids = []

        for vendor_id, items in vendor_items_map.items():
            # Calculate subtotal for this vendor
            
            subtotal = sum(item['price'] * item['quantity'] for item in items)
            print(f"subtotal =========== {subtotal}")
            # Apply delivery fee and discount
            # fees= await RiderFeesAndBonuses.filter().first()
            # delivery_fee = fees.rider_delivery_fee
            delivery_fee = Decimal(str(order_data.delivery_option.price))
            print(f"delivery_fee =========== {delivery_fee}")

            # coupon_discount = self._apply_coupon(subtotal, order_data.coupon_code)
            total = subtotal + delivery_fee - discount_per_order
            print(f"total =========== {total}")
            
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
            
            # order_status_update = OrderStatus.PROCESSING if order_data.payment_method.type != "cashfree" else OrderStatus.PENDING

            if order_data.payment_method.type == "phonepe" or order_data.payment_method.type == "cashfree":
                order_status_update = OrderStatus.PENDING
            else:
                order_status_update = OrderStatus.PROCESSING


            # Create order with parent_order_id
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
                discount=discount_per_order,
                status=order_status_update,   
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

                order_id = self._generate_order_id()
                order = await Order.create(
                    id=order_id,
                    parent_order_id=parent_order_id,
                    user_id=current_user.id,
                    vendor_id=vendor_id,
                    shipping_address_id=None,
                    delivery_type=order_data.delivery_option.type,
                    payment_method=order_data.payment_method.type,
                    subtotal=subtotal,
                    delivery_fee=delivery_fee,
                    total=total,
                    coupon_code=order_data.coupon_code,
                    discount=discount_per_order,
                    status=order_status_update,
                    payment_status="unpaid",
                    tracking_number=self._generate_tracking_number(),
                    estimated_delivery=self._calculate_estimated_delivery(
                        order_data.delivery_option.type
                    ),
                    metadata=order_metadata,
                    is_combined=False
                )

                for item_data in items:
                    await OrderItem.create(
                        order_id=order.id,
                        item_id=item_data['item'].id,
                        title=item_data['title'],
                        price=str(item_data["price"]),
                        quantity=item_data['quantity'],
                        image_path=item_data['image_path']
                    )

                await order.fetch_related("user", "items__item")
                created_orders.append(order)
                related_order_ids.append(order_id)
                print(f"[ORDER] Created split order {order.id} for vendor {vendor_id}")

            except Exception as e:
                print(f"[ERROR] Failed to create split order for vendor {vendor_id}: {e}")
                for created_order in created_orders:
                    await created_order.delete()
                raise

        # Store related order IDs in metadata
        for order in created_orders:
            if order.metadata:
                order.metadata['related_order_ids'] = [oid for oid in related_order_ids if oid != order.id]
            else:
                order.metadata = {'related_order_ids': [oid for oid in related_order_ids if oid != order.id]}
            await order.save()

        return created_orders

    async def _create_urgent_orders(
        self,
        vendor_items_map: Dict[int, List[Dict]],
        order_data: OrderCreateSchema,
        current_user
    ) -> List[Order]:
        """
        Create urgent orders. One order per urgent item vendor.
        Rider is automatically assigned after vendor confirmation.
        """
        created_orders = []
        parent_order_id = self._generate_parent_order_id()

        grand_subtotal = Decimal("0")
        for items in vendor_items_map.values():
            grand_subtotal += sum(item["price"] * item['quantity'] for item in items)

        total_coupon_discount = self._apply_coupon(grand_subtotal, order_data.coupon_code)
        vendor_count = len(vendor_items_map)
        discount_per_order = total_coupon_discount / vendor_count if vendor_count > 0 else Decimal("0")

        for vendor_id, items in vendor_items_map.items():
            try:
                subtotal = sum(item["price"] * item['quantity'] for item in items)
                delivery_fee = Decimal(str(order_data.delivery_option.price))
                total = subtotal + delivery_fee - discount_per_order

                first_item_vendor = items[0]['vendor']
                vendor_profile = await VendorProfile.get_or_none(user=first_item_vendor)
                
                vendor_info = self._build_vendor_info(first_item_vendor, vendor_profile)
                order_metadata = self._build_order_metadata(order_data, vendor_info, "urgent")

                order_status_update = (
                    OrderStatus.PROCESSING 
                    if order_data.payment_method.type != "cashfree" 
                    else OrderStatus.PENDING
                )
                delivery_type = "urgent"

                order_id = self._generate_order_id()
                order = await Order.create(
                    id=order_id,
                    parent_order_id=parent_order_id,
                    user_id=current_user.id,
                    vendor_id=vendor_id,
                    shipping_address_id=None,
                    delivery_type=delivery_type,
                    # delivery_type=order_data.delivery_option.type,
                    payment_method=order_data.payment_method.type,
                    subtotal=subtotal,
                    delivery_fee=delivery_fee,
                    total=total,
                    coupon_code=order_data.coupon_code,
                    discount=discount_per_order,
                    status=order_status_update,
                    payment_status="unpaid",
                    tracking_number=self._generate_tracking_number(),
                    estimated_delivery=self._calculate_estimated_delivery(
                        order_data.delivery_option.type
                    ),
                    metadata=order_metadata,
                    is_combined=False
                )

                for item_data in items:
                    await OrderItem.create(
                        order_id=order.id,
                        item_id=item_data['item'].id,
                        title=item_data['title'],
                        price=str(item_data["price"]),
                        quantity=item_data['quantity'],
                        image_path=item_data['image_path']
                    )

                await order.fetch_related("user", "items__item")
                created_orders.append(order)
                print(f"[ORDER] Created urgent order {order.id} for vendor {vendor_id}")

            except Exception as e:
                print(f"[ERROR] Failed to create urgent order for vendor {vendor_id}: {e}")
                for created_order in created_orders:
                    await created_order.delete()
                raise

        return created_orders

    async def _create_mixed_orders(
        self,
        urgent_vendors: Dict[int, List[Dict]],
        non_urgent_vendors: Dict[int, List[Dict]],
        order_data: OrderCreateSchema,
        current_user
    ) -> List[Order]:
        """Create mixed orders: urgent + combined"""
        created_orders = []

        print(f"[ORDER] Creating urgent orders for {len(urgent_vendors)} vendors")
        urgent_orders = await self._create_urgent_orders(urgent_vendors, order_data, current_user)
        created_orders.extend(urgent_orders)

        print(f"[ORDER] Creating combined orders for {len(non_urgent_vendors)} vendors")
        combined_orders = await self._create_combined_orders(non_urgent_vendors, order_data, current_user)
        created_orders.extend(combined_orders)

        return created_orders

    def _build_vendor_info(self, vendor_user, vendor_profile) -> dict:
        """Build vendor information dictionary"""
        vendor_info = {
            "vendor_id": vendor_user.id,
            "vendor_name": vendor_user.name,
            "vendor_phone": vendor_user.phone,
            "vendor_email": vendor_user.email or None,
            "is_vendor": vendor_user.is_vendor,
            "is_active": vendor_user.is_active
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

        return vendor_info

    def _build_order_metadata(
        self,
        order_data: OrderCreateSchema,
        vendor_info: dict,
        order_type: str
    ) -> dict:
        """Build order metadata"""
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

        return {
            "order_type": order_type,
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
