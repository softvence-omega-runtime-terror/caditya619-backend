# from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Query, Request
# from datetime import datetime, date, timedelta, timezone
# from decimal import Decimal
# from pydantic import BaseModel
# from typing import Optional, List, Dict, Tuple
# import logging
# import json
# import asyncio

# from applications.user.models import User
# from applications.user.rider import (
#     RiderProfile, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses, OrderOffer
# )
# from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
# from applications.items.models import Item
# from applications.user.vendor import VendorProfile
# from applications.user.customer import CustomerProfile
# from applications.earning.vendor_earning import add_money_to_vendor_account
# from tortoise.contrib.pydantic import pydantic_model_creator

# from app.token import get_current_user
# from app.utils.geo import haversine, bbox_for_radius, estimate_eta
# from app.utils.websocket_manager import manager
# from app.redis import get_redis

# from tortoise.transactions import in_transaction
# from tortoise.exceptions import IntegrityError

# from .notifications import send_notification
# from .websocket_endpoints import start_chat, end_chat, subscribe_to_riders_location
# from app.utils.translator import translate

# # ============================================================================
# # CONFIGURATION & LOGGING
# # ============================================================================

# logger = logging.getLogger(__name__)
# router = APIRouter(tags=['Rider Orders'])

# # # Constants
# # OFFER_TIMEOUT_SECONDS = 1200  # 20 minutes total offer validity
# # URGENT_OFFER_TIMEOUT = 60     # 1 minute per rider for urgent orders
# # SPLIT_BROADCAST_TIMEOUT = 60  # 1 minute to accept for split/combined

# # GEO_REDIS_KEY = "riders_geo"
# # INITIAL_RADIUS_KM = 3.0
# # RADIUS_STEP_KM = 1.0
# # MAX_RADIUS_KM = 20.0
# # URGENT_RADIUS_KM = 10.0

# # # ============================================================================
# # # PYDANTIC MODELS
# # # ============================================================================

# # OrderOut = pydantic_model_creator(Order, name='OrderOut')

# # class OrderRejectRequest(BaseModel):
# #     """Rejection request with reason"""
# #     order_id: str
# #     reason: str

# # class RiderStatsResponse(BaseModel):
# #     """Rider statistics for tracking rejections"""
# #     total_offers: int
# #     rejections: int
# #     timeout_rejections: int
# #     acceptance_rate: float

# # # ============================================================================
# # # HELPER FUNCTIONS
# # # ============================================================================

# # def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
# #     """Convert datetime to UTC if not already"""
# #     if dt is None:
# #         return None
# #     if dt.tzinfo is None:
# #         return dt.replace(tzinfo=timezone.utc)
# #     return dt.astimezone(timezone.utc)


# # async def notify_rider_websocket(
# #     rider_id: int,
# #     order: Order,
# #     notification_type: str = "order_offer"
# # ) -> bool:
# #     """
# #     Send WebSocket notification to rider.
# #     Returns: True if successful, False otherwise
# #     """
# #     try:
# #         payload = {
# #             "type": notification_type,
# #             "order_id": str(order.id),
# #             "timestamp": datetime.utcnow().isoformat(),
# #             "delivery_type": str(order.delivery_type)
# #         }

# #         rider = await RiderProfile.get_or_none(id=rider_id)
# #         if not rider:
# #             logger.error(f"Rider {rider_id} not found for WebSocket notification")
# #             return False

# #         # Send via WebSocket manager
# #         await manager.send_notification(
# #             "riders",
# #             str(rider.user_id),
# #             "New Order Offer",
# #             f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
# #         )
# #         logger.info(f"WebSocket notification sent to rider {rider_id} for order {order.id}")
# #         return True

# #     except Exception as e:
# #         logger.error(f"WebSocket notification error for rider {rider_id}: {str(e)}")
# #         return False


# # async def notify_rider_pushnotification(
# #     rider_id: int,
# #     title: str,
# #     body: str
# # ) -> bool:
# #     """
# #     Send push notification to rider.
# #     Returns: True if successful, False otherwise
# #     """
# #     try:
# #         rider = await RiderProfile.get_or_none(id=rider_id)
# #         if not rider or not rider.user_id:
# #             logger.warning(f"Rider {rider_id} not found or no user_id for push notification")
# #             return False

# #         await send_notification(rider.user_id, title, body)
# #         logger.info(f"Push notification sent to rider {rider_id}: {title}")
# #         return True

# #     except Exception as e:
# #         logger.error(f"Push notification error for rider {rider_id}: {str(e)}")
# #         return False


# # async def find_candidate_riders(
# #     vendor_lat: float,
# #     vendor_lng: float,
# #     is_urgent: bool = False,
# #     top_n: int = 20,
# #     redis=None
# # ) -> List[RiderProfile]:
# #     """
# #     Find eligible rider candidates based on location and availability.
    
# #     Strategy:
# #     1. Try Redis GEO search (GEORADIUS for Redis < 6.2 compatibility)
# #     2. Fall back to database query
# #     3. Expand radius progressively if needed
# #     """
# #     candidates = []
# #     radius = URGENT_RADIUS_KM if is_urgent else INITIAL_RADIUS_KM
# #     max_radius = URGENT_RADIUS_KM if is_urgent else MAX_RADIUS_KM
# #     existing_ids = set()

# #     while len(candidates) < top_n and radius <= max_radius:
# #         candidate_rider_ids = []

# #         # Try Redis GEO search (GEORADIUS for compatibility)
# #         if redis:
# #             try:
# #                 # Use GEORADIUS instead of GEOSEARCH for Redis < 6.2 compatibility
# #                 geo_res = await redis.execute_command(
# #                     "GEORADIUS",
# #                     GEO_REDIS_KEY,
# #                     vendor_lng,
# #                     vendor_lat,
# #                     radius,
# #                     "km",
# #                     "ASC",
# #                     "COUNT",
# #                     int(top_n * 3)
# #                 )

# #                 if geo_res:
# #                     candidate_rider_ids = [
# #                         int(x) for x in geo_res
# #                         if int(x) not in existing_ids
# #                     ]

# #             except Exception as e:
# #                 logger.warning(f"Redis GEORADIUS search failed: {str(e)}")
# #                 candidate_rider_ids = []

# #         # Get riders from database
# #         try:
# #             if candidate_rider_ids:
# #                 riders = await RiderProfile.filter(
# #                     id__in=candidate_rider_ids,
# #                     is_available=True
# #                 ).prefetch_related("current_location").all()
# #             else:
# #                 # Fallback: query all available riders
# #                 riders = await RiderProfile.filter(
# #                     is_available=True
# #                 ).prefetch_related("current_location").all()

# #             # Calculate distances and filter by radius
# #             rider_distances = []
# #             for r in riders:
# #                 if r.id in existing_ids:
# #                     continue

# #                 loc = r.current_location
# #                 if not loc:
# #                     continue

# #                 dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
# #                 if dist <= radius:
# #                     rider_distances.append((r, dist))
# #                     existing_ids.add(r.id)

# #             # Sort by distance and append
# #             rider_distances.sort(key=lambda x: x[1])
# #             candidates.extend(rider_distances)

# #         except Exception as e:
# #             logger.error(f"Database query error at radius {radius}km: {str(e)}")

# #         radius += RADIUS_STEP_KM

# #     # Remove duplicates and return top N
# #     seen_ids = set()
# #     result = []
# #     for rider, _ in candidates:
# #         if rider.id not in seen_ids:
# #             result.append(rider)
# #             seen_ids.add(rider.id)
# #             if len(result) >= top_n:
# #                 break

# #     logger.info(f"Found {len(result)} candidate riders (urgent={is_urgent})")
# #     return result


# # async def send_offer_to_rider(
# #     order_id: str,
# #     rider_id: int,
# #     is_urgent: bool = False
# # ) -> bool:
# #     """
# #     Send order offer to a single rider (used for broadcast offers).
# #     Creates OrderOffer record and sends notifications.
# #     Returns: True if successful
# #     """
# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         rider = await RiderProfile.get_or_none(id=rider_id)

# #         if not order or not rider:
# #             logger.error(f"Order {order_id} or Rider {rider_id} not found")
# #             return False

# #         # Create OrderOffer record
# #         offer = await OrderOffer.create(
# #             order=order,
# #             rider=rider,
# #             status="PENDING",
# #             is_urgent=is_urgent,
# #             created_at=datetime.utcnow()
# #         )

# #         # Send WebSocket notification
# #         ws_success = await notify_rider_websocket(rider_id, order, "order_offer")

# #         # Send push notification
# #         is_urgent_order = order.delivery_type == DeliveryTypeEnum.URGENT
# #         notification_title = "🚨 URGENT: Medicine Delivery" if is_urgent_order else "New Order Offer"
# #         notification_body = f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
# #         push_success = await notify_rider_pushnotification(rider_id, notification_title, notification_body)

# #         # Update WorkDay stats
# #         today = date.today()
# #         workday, _ = await WorkDay.get_or_create(
# #             rider=rider,
# #             date=today,
# #             defaults={"hours_worked": 0.0, "order_offer_count": 0}
# #         )
# #         workday.order_offer_count += 1
# #         await workday.save()

# #         logger.info(f"Offer sent to rider {rider_id} for order {order_id}")
# #         return ws_success or push_success

# #     except Exception as e:
# #         logger.error(f"Error sending offer to rider {rider_id}: {str(e)}")
# #         return False


# # async def offer_order_sequentially(
# #     order_id: str,
# #     candidate_riders: List[RiderProfile],
# #     background_tasks: BackgroundTasks
# # ):
# #     """
# #     Offer order to riders sequentially with timeout logic.
    
# #     For URGENT orders:
# #     - Offer to one rider, wait 60 seconds for response
# #     - If no response, mark as TIMEOUT and move to next rider
# #     - Move to next immediately if rejected
    
# #     For NORMAL orders:
# #     - Offer and continue immediately (no wait)
# #     """
# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             logger.error(f"Order {order_id} not found for sequential offering")
# #             return

# #         is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT

# #         for idx, rider in enumerate(candidate_riders):
# #             # Check if order is still available (not yet accepted)
# #             await order.refresh_from_db()
# #             if order.status != OrderStatus.PROCESSING:
# #                 logger.info(f"Order {order_id} already accepted, stopping offers")
# #                 break

# #             try:
# #                 # Send offer to this rider
# #                 success = await send_offer_to_rider(order.id, rider.id, is_urgent)
# #                 if not success:
# #                     logger.warning(f"Failed to send offer to rider {rider.id}")

# #                 logger.info(f"Order {order_id} offered to rider {rider.id} ({idx + 1}/{len(candidate_riders)})")

# #                 if is_urgent:
# #                     # Wait 60 seconds for urgent order
# #                     await asyncio.sleep(URGENT_OFFER_TIMEOUT)

# #                     # Check if rider accepted or rejected
# #                     await order.refresh_from_db()
# #                     offer = await OrderOffer.filter(
# #                         order=order,
# #                         rider=rider
# #                     ).first()

# #                     if offer and offer.status == "PENDING":
# #                         # Auto-timeout: mark as timeout
# #                         offer.status = "TIMEOUT"
# #                         offer.responded_at = datetime.utcnow()
# #                         await offer.save()
# #                         logger.info(f"Offer to rider {rider.id} timed out (60s)")
# #                         # Continue to next rider
# #                     elif offer and offer.status == "REJECTED":
# #                         logger.info(f"Rider {rider.id} rejected order {order_id}")
# #                         # Continue to next rider
# #                     elif offer and offer.status == "ACCEPTED":
# #                         # Rider accepted - order will be marked as accepted elsewhere
# #                         break
# #                 else:
# #                     # For non-urgent, just continue immediately
# #                     pass

# #             except asyncio.CancelledError:
# #                 logger.warning(f"Sequential offering task cancelled for order {order_id}")
# #                 break
# #             except Exception as e:
# #                 logger.error(f"Error offering order {order_id} to rider {rider.id}: {str(e)}")
# #                 continue

# #     except Exception as e:
# #         logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")


# # async def offer_order_broadcast(
# #     order_id: str,
# #     candidate_riders: List[RiderProfile],
# #     background_tasks: BackgroundTasks
# # ):
# #     """
# #     Offer order to all riders simultaneously (for SPLIT and COMBINED orders).
    
# #     First rider to accept wins.
# #     Others count offer but don't get accepted.
# #     """
# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             logger.error(f"Order {order_id} not found for broadcast offering")
# #             return

# #         # Send offers to all riders concurrently
# #         tasks = [
# #             send_offer_to_rider(order.id, rider.id, is_urgent=False)
# #             for rider in candidate_riders
# #         ]

# #         results = await asyncio.gather(*tasks, return_exceptions=True)
# #         successful = sum(1 for r in results if r is True)

# #         logger.info(f"Broadcast offers sent to {len(candidate_riders)} riders for order {order_id} ({successful} successful)")

# #         # Wait for acceptance (rider will accept in accept_order endpoint)
# #         # This task just sends the offers

# #     except Exception as e:
# #         logger.error(f"Error in broadcast offering for order {order_id}: {str(e)}")


# # # ============================================================================
# # # ORDER ENDPOINTS
# # # ============================================================================

# # @router.post("/orders/create-offer/{order_id}/")
# # async def create_order_offer(
# #     request: Request,
# #     order_id: str,
# #     background_tasks: BackgroundTasks,
# #     prepare_time: int = Form(...),
# #     top_n: int = 20,
# #     current_user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     Create order offer and find eligible riders.
# #     Called by VENDOR after order is placed.
    
# #     Flow:
# #     1. Find candidate riders based on location
# #     2. Validate order details
# #     3. For SPLIT/COMBINED: broadcast to all riders
# #     4. For URGENT: sequential with 1-minute timeouts per rider
# #     5. For NORMAL: sequential without timeouts
    
# #     Returns: Offer creation status with candidate count
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     if not current_user.is_vendor:
# #         raise HTTPException(status_code=403, detail=translate("Only vendors can create offers", lang))

# #     if top_n <= 0 or top_n > 100:
# #         raise HTTPException(status_code=400, detail=translate("Invalid top_n parameter (1-100)", lang))

# #     try:
# #         # Validate order exists and get related entities
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail=translate("Order not found", lang))

# #         order_item = await OrderItem.get_or_none(order=order)
# #         if not order_item:
# #             raise HTTPException(status_code=404, detail=translate("Order item not found", lang))

# #         item = await Item.get_or_none(id=order_item.item_id)
# #         if not item:
# #             raise HTTPException(status_code=404, detail="Item not found")

# #         vendor = await VendorProfile.get_or_none(id=item.vendor_id)
# #         if not vendor:
# #             raise HTTPException(status_code=404, detail="Vendor not found")

# #         customer = await CustomerProfile.get_or_none(id=order.user_id)
# #         if not customer:
# #             raise HTTPException(status_code=404, detail="Customer not found")

# #         # Validate order is in correct status
# #         if order.status not in [OrderStatus.PENDING, OrderStatus.PROCESSING]:
# #             raise HTTPException(status_code=400, detail="Order already being processed or delivered")

# #         # Determine delivery type
# #         is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
# #         is_split = order.delivery_type == DeliveryTypeEnum.SPLIT
# #         is_combined = order.is_combined or (order.delivery_type == DeliveryTypeEnum.COMBINED)

# #         # Find candidate riders
# #         candidates = await find_candidate_riders(
# #             vendor.latitude,
# #             vendor.longitude,
# #             is_urgent=is_urgent,
# #             top_n=top_n,
# #             redis=redis
# #         )

# #         if not candidates:
# #             raise HTTPException(status_code=400, detail="No riders available in area")

# #         # Update order status to PROCESSING (waiting for acceptance)
# #         order.status = OrderStatus.CONFIRMED
# #         order.metadata = order.metadata or {}
# #         order.metadata["candidate_riders"] = [r.id for r in candidates]
# #         order.metadata["offered_at"] = datetime.utcnow().isoformat()
# #         order.metadata["delivery_type"] = str(order.delivery_type)
# #         order.prepare_time = prepare_time
# #         await order.save()

# #         # Deduct stock
# #         item.stock -= order_item.quantity
# #         await item.save()

# #         # Queue offering based on order type
# #         if is_split or is_combined:
# #             # Broadcast to all riders simultaneously
# #             background_tasks.add_task(
# #                 offer_order_broadcast,
# #                 order_id,
# #                 candidates,
# #                 background_tasks
# #             )
# #         else:
# #             # Sequential offering (for URGENT and NORMAL)
# #             background_tasks.add_task(
# #                 offer_order_sequentially,
# #                 order_id,
# #                 candidates,
# #                 background_tasks
# #             )

# #         return translate({
# #             "status": "offer_created",
# #             "order_id": order_id,
# #             "candidate_count": len(candidates),
# #             "delivery_type": str(order.delivery_type),
# #             "is_urgent": is_urgent,
# #             "is_split": is_split,
# #             "is_combined": is_combined,
# #             "message": f"Order offers sent to {len(candidates)} nearby riders"
# #         }, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error creating order offer: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/accept/{order_id}/")
# # async def accept_order(
# #     request: Request,
# #     order_id: str,
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     RIDER accepts an order.
    
# #     Flow:
# #     1. Claim order via Redis (race condition prevention)
# #     2. Validate order status and delivery type restrictions
# #     3. Verify location data
# #     4. Calculate payout
# #     5. Update order with rider assignment
# #     6. Mark this offer as ACCEPTED
# #     7. Reject other pending offers for this order
# #     8. Send notifications
# #     9. Start chat channels
    
# #     Restrictions:
# #     - URGENT/SPLIT: Cannot accept another order until delivered
# #     - COMBINED: Can accept other orders
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         # Get rider profile
# #         rider_profile = await RiderProfile.get_or_none(user=user)
# #         if not rider_profile:
# #             raise HTTPException(status_code=403, detail="Not a rider profile")

# #         # Use Redis to prevent race condition
# #         claim_key = f"order_claim:{order_id}"
# #         claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)

# #         if not claimed:
# #             raise HTTPException(status_code=400, detail="Order already claimed by another rider")

# #         # Get and validate order
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             await redis.delete(claim_key)
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         # Order must be in PROCESSING state
# #         if order.status != OrderStatus.CONFIRMED:
# #             await redis.delete(claim_key)
# #             raise HTTPException(status_code=400, detail="Order not available (already accepted or expired)")

# #         # Check delivery type restrictions
# #         is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
# #         is_split = order.delivery_type == DeliveryTypeEnum.SPLIT
# #         is_combined = order.is_combined or (order.delivery_type == DeliveryTypeEnum.COMBINED)

# #         # URGENT and SPLIT orders: cannot accept another until delivered
# #         if is_urgent or is_split:
# #             active_blocking = await Order.filter(
# #                 rider=rider_profile,
# #                 delivery_type__in=[DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT],
# #                 status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
# #             ).first()

# #             if active_blocking:
# #                 await redis.delete(claim_key)
# #                 raise HTTPException(
# #                     status_code=400,
# #                     detail="Cannot accept another urgent/split order until current delivery is complete"
# #                 )

# #         # COMBINED orders: no restriction (can accept multiple)
# #         # (other delivery types also have no restriction)

# #         async with in_transaction():
# #             # Re-verify order status inside transaction
# #             order = await Order.get(id=order_id)
# #             if order.status != OrderStatus.CONFIRMED:
# #                 raise HTTPException(status_code=400, detail="Order not available")

# #             # Get all required data
# #             order_item = await OrderItem.get_or_none(order=order)
# #             if not order_item:
# #                 raise HTTPException(status_code=404, detail="Order item not found")

# #             item = await Item.get_or_none(id=order_item.item_id)
# #             if not item:
# #                 raise HTTPException(status_code=404, detail="Item not found")

# #             vendor = await VendorProfile.get_or_none(id=item.vendor_id)
# #             if not vendor:
# #                 raise HTTPException(status_code=404, detail="Vendor not found")

# #             customer = await CustomerProfile.get_or_none(id=order.user_id)
# #             if not customer:
# #                 raise HTTPException(status_code=404, detail="Customer not found")

# #             loc = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
# #             if not loc:
# #                 raise HTTPException(status_code=400, detail="Rider location not available")

# #             # Get fees configuration
# #             fees_config = await RiderFeesAndBonuses.get_or_none(id=1)
# #             if not fees_config:
# #                 raise HTTPException(status_code=500, detail="Fees not configured")

# #             # Calculate distances
# #             pickup_dist = haversine(
# #                 vendor.latitude, vendor.longitude,
# #                 loc.latitude, loc.longitude
# #             )

# #             delivery_dist = haversine(
# #                 vendor.latitude, vendor.longitude,
# #                 customer.customer_lat, customer.customer_lng
# #             )

# #             total_dist = pickup_dist + delivery_dist

# #             # Calculate payout
# #             base_rate = float(fees_config.rider_delivery_fee or 44.00)

# #             # Distance bonus: ₹1 per km beyond 3km
# #             distance_bonus = max(total_dist - 3, 0) * float(fees_config.distance_bonus_per_km or 1.0)

# #             # For combined orders, add base rate for each additional pickup
# #             if is_combined and order.combined_pickups:
# #                 base_rate += (len(order.combined_pickups) - 1) * base_rate

# #             # Estimate ETA
# #             pickup_eta_min = int(estimate_eta(pickup_dist).total_seconds() / 60)
# #             delivery_eta_min = int(estimate_eta(delivery_dist).total_seconds() / 60)
# #             eta_minutes = pickup_eta_min + delivery_eta_min + (order.prepare_time or 10)

# #             # Update order
# #             #order.status = OrderStatus.CONFIRMED
# #             order.rider = rider_profile
# #             order.pickup_distance_km = Decimal(str(round(pickup_dist, 2)))
# #             order.base_rate = Decimal(str(base_rate))
# #             order.distance_bonus = Decimal(str(round(distance_bonus, 2)))
# #             order.eta_minutes = eta_minutes
# #             order.accepted_at = datetime.utcnow()
# #             order.expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
# #             order.metadata = order.metadata or {}
# #             order.metadata["rider_id"] = rider_profile.id
# #             order.metadata["accepted_at"] = datetime.utcnow().isoformat()

# #             await order.save()

# #             # Update the OrderOffer record for this rider to ACCEPTED
# #             offer = await OrderOffer.filter(order=order, rider=rider_profile).first()
# #             if offer:
# #                 offer.status = "ACCEPTED"
# #                 offer.responded_at = datetime.utcnow()
# #                 await offer.save()

# #             # Reject all other pending offers for this order
# #             await OrderOffer.filter(
# #                 order=order
# #             ).exclude(rider=rider_profile).update(
# #                 status="REJECTED",
# #                 responded_at=datetime.utcnow()
# #             )

# #         # Send WebSocket notification to customer and vendor
# #         notify_payload = {
# #             "type": "order_accepted",
# #             "order_id": order_id,
# #             "rider_id": rider_profile.id,
# #             "rider_name": user.name,
# #             "accepted_at": datetime.utcnow().isoformat()
# #         }

# #         await redis.publish("order_updates", json.dumps(notify_payload))

# #         try:
# #             await manager.send_notification(
# #                 "customers",
# #                 str(order.user_id),
# #                 "Rider Assigned",
# #                 f"{user.name} is on the way!"
# #             )
# #             await manager.send_notification(
# #                 "vendors",
# #                 str(vendor.user_id),
# #                 "Rider Assigned",
# #                 f"Rider {user.name} assigned to order {order_id}"
# #             )
# #         except Exception as e:
# #             logger.warning(f"WebSocket notification failed: {str(e)}")

# #         # Send push notifications
# #         try:
# #             await send_notification(
# #                 order.user_id,
# #                 "Rider Assigned",
# #                 f"Rider {user.name} is on the way!"
# #             )

# #             await send_notification(
# #                 vendor.user_id,
# #                 "Order Confirmed",
# #                 f"Order {order_id} confirmed with rider {user.name}"
# #             )
# #         except Exception as e:
# #             logger.error(f"Push notification error: {str(e)}")

# #         # Start chat channels
# #         customer_message = None
# #         vendor_message = None
# #         location_subscribe = None

# #         try:
# #             customer_message = await start_chat("riders", user.id, "customers", order.user_id)
# #             vendor_message = await start_chat("riders", user.id, "vendors", vendor.user_id)
# #             location_subscribe = await subscribe_to_riders_location("subscribe", user.id, order.user_id)
# #         except Exception as e:
# #             logger.error(f"Chat initialization error: {str(e)}")

# #         # Clean up Redis claim
# #         await redis.delete(claim_key)

# #         return translate({
# #             "status": "order_accepted",
# #             "order_id": order_id,
# #             "rider_id": rider_profile.user_id,
# #             "payout": float(order.base_rate + order.distance_bonus),
# #             "base_rate": float(order.base_rate),
# #             "distance_bonus": float(order.distance_bonus),
# #             "eta_minutes": order.eta_minutes,
# #             "customer_message": customer_message,
# #             "vendor_message": vendor_message,
# #             "location_subscribe": location_subscribe
# #         }, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error accepting order: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/reject/{order_id}/")
# # async def reject_order(
# #     request: Request,
# #     order_id: str,
# #     reason: str = Form(...),
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     RIDER rejects an order.
    
# #     For URGENT orders: reason is mandatory and tracked.
# #     For other orders: reason is optional but recommended.
    
# #     Updates:
# #     - OrderOffer status to REJECTED
# #     - WorkDay rejection count
# #     - Logs rejection for audit trail
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         rider = await RiderProfile.get_or_none(user=user)
# #         if not rider:
# #             raise HTTPException(status_code=403, detail="Not a rider")

# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         # Check if order is still in PROCESSING
# #         if order.status != OrderStatus.PROCESSING:
# #             raise HTTPException(status_code=400, detail="Order not available for rejection")

# #         is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT

# #         # For urgent orders, reason is required
# #         if is_urgent and not reason.strip():
# #             raise HTTPException(status_code=400, detail="Reason is required for urgent order rejection")

# #         # Get the most recent offer for this rider
# #         offer = await OrderOffer.filter(
# #             order=order,
# #             rider=rider
# #         ).order_by("-created_at").first()

# #         if not offer:
# #             raise HTTPException(status_code=400, detail="No active offer for this order")

# #         if offer.status != "PENDING":
# #             raise HTTPException(status_code=400, detail="Offer already responded to")

# #         # Update offer
# #         offer.status = "REJECTED"
# #         offer.reject_reason = reason
# #         offer.responded_at = datetime.utcnow()
# #         await offer.save()

# #         # Update WorkDay stats
# #         today = date.today()
# #         workday, _ = await WorkDay.get_or_create(
# #             rider=rider,
# #             date=today,
# #             defaults={"hours_worked": 0.0, "order_offer_count": 0, "rejection_count": 0}
# #         )
# #         if not hasattr(workday, 'rejection_count'):
# #             workday.rejection_count = 0
# #         workday.rejection_count += 1
# #         await workday.save()

# #         logger.info(f"Order {order_id} rejected by rider {rider.id}. Reason: {reason}")

# #         return translate({
# #             "status": "rejected",
# #             "order_id": order_id,
# #             "reason": reason,
# #             "is_urgent": is_urgent
# #         }, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error rejecting order: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/shipped/{order_id}/")
# # async def mark_order_shipped(
# #     request: Request,
# #     order_id: str,
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     VENDOR marks order as shipped (picked up by rider).
# #     Flow: CONFIRMED -> SHIPPED
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     if not user.is_vendor:
# #         raise HTTPException(status_code=403, detail="Only vendors can mark shipped")

# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         if order.status != OrderStatus.CONFIRMED:
# #             raise HTTPException(status_code=400, detail="Order must be confirmed first")

# #         order.status = OrderStatus.SHIPPED
# #         order.shipped_at = datetime.utcnow()
# #         await order.save()

# #         notify_payload = {
# #             "type": "order_shipped",
# #             "order_id": order_id,
# #             "shipped_at": datetime.utcnow().isoformat()
# #         }

# #         await redis.publish("order_updates", json.dumps(notify_payload))

# #         try:
# #             await manager.send_notification(
# #                 "customers",
# #                 str(order.user_id),
# #                 "Order Picked Up",
# #                 "Your order has been picked up!"
# #             )
# #             await send_notification(order.user_id, "Order Shipped", "Your order is on the way!")
# #         except Exception as e:
# #             logger.warning(f"Shipment notification error: {str(e)}")

# #         return translate({"status": "shipped", "order_id": order_id}, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error marking shipped: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/out-for-delivery/{order_id}/")
# # async def mark_order_out_for_delivery(
# #     request: Request,
# #     order_id: str,
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     RIDER marks order as out for delivery.
# #     Flow: SHIPPED -> OUT_FOR_DELIVERY
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     if not user.is_rider:
# #         raise HTTPException(status_code=403, detail="Only riders can update this")

# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         if order.status != OrderStatus.SHIPPED:
# #             raise HTTPException(status_code=400, detail="Order not in shipped status")

# #         order.status = OrderStatus.OUT_FOR_DELIVERY
# #         order.out_for_delivery_at = datetime.utcnow()
# #         await order.save()

# #         notify_payload = {
# #             "type": "order_out_for_delivery",
# #             "order_id": order_id,
# #             "out_for_delivery_at": datetime.utcnow().isoformat()
# #         }

# #         await redis.publish("order_updates", json.dumps(notify_payload))

# #         try:
# #             await manager.send_notification(
# #                 "customers",
# #                 str(order.user_id),
# #                 "Out for Delivery",
# #                 "Your order is arriving soon!"
# #             )
# #             await send_notification(order.user_id, "Out for Delivery", "Your order is on its way!")
# #         except Exception as e:
# #             logger.warning(f"Out for delivery notification error: {str(e)}")

# #         return translate({"status": "out_for_delivery", "order_id": order_id}, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error marking out for delivery: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/delivered/{order_id}/")
# # async def mark_order_delivered(
# #     request: Request,
# #     order_id: str,
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     RIDER marks order as delivered.
# #     Flow: OUT_FOR_DELIVERY -> DELIVERED
    
# #     - Check if on-time delivery
# #     - Update rider balance
# #     - Send notifications
# #     - End chat sessions
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     if not user.is_rider:
# #         raise HTTPException(status_code=403, detail="Only riders can mark delivered")

# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         order_item = await OrderItem.get_or_none(order=order)
# #         if not order_item:
# #             raise HTTPException(status_code=404, detail="Order item not found")

# #         item = await Item.get_or_none(id=order_item.item_id)
# #         if not item:
# #             raise HTTPException(status_code=404, detail="Item not found")

# #         vendor = await VendorProfile.get_or_none(id=item.vendor_id)
# #         if not vendor:
# #             raise HTTPException(status_code=404, detail="Vendor not found")

# #         if order.status != OrderStatus.OUT_FOR_DELIVERY:
# #             raise HTTPException(status_code=400, detail="Order not out for delivery")

# #         # Check if on-time
# #         now = datetime.now(timezone.utc)
# #         accepted_at = to_utc(order.accepted_at)

# #         if accepted_at and order.eta_minutes:
# #             eta_deadline = accepted_at + timedelta(minutes=order.eta_minutes)
# #             order.is_on_time = now <= eta_deadline
# #         else:
# #             order.is_on_time = True

# #         # Update order
# #         order.status = OrderStatus.DELIVERED
# #         order.completed_at = now
# #         await order.save()

# #         # Update rider balance
# #         rider = await RiderProfile.get_or_none(id=order.rider_id)
# #         if rider:
# #             payout = float(order.base_rate or 0) + float(order.distance_bonus or 0)
# #             rider.current_balance += Decimal(str(payout))
# #             await rider.save()
# #             logger.info(f"Rider {rider.id} balance updated: +₹{payout}")

# #         # Add money to vendor account
# #         try:
# #             await add_money_to_vendor_account(order.id)
# #         except Exception as e:
# #             logger.warning(f"Error adding money to vendor account: {str(e)}")

# #         # Send notifications
# #         notify_payload = {
# #             "type": "order_delivered",
# #             "order_id": order_id,
# #             "delivered_at": now.isoformat(),
# #             "is_on_time": order.is_on_time,
# #             "payout": float(order.base_rate or 0) + float(order.distance_bonus or 0)
# #         }

# #         await redis.publish("order_updates", json.dumps(notify_payload))

# #         try:
# #             await manager.send_notification(
# #                 "customers",
# #                 str(order.user_id),
# #                 "Order Delivered",
# #                 "Thank you for your order!"
# #             )
# #             await manager.send_notification(
# #                 "vendors",
# #                 str(vendor.user_id),
# #                 "Order Delivered",
# #                 f"Order {order_id} delivered successfully!"
# #             )
# #             await send_notification(order.user_id, "Order Delivered", "Thank you for your order!")
# #         except Exception as e:
# #             logger.warning(f"Delivery notification error: {str(e)}")

# #         # End chat
# #         try:
# #             await end_chat("riders", user.id, "customers", order.user_id)
# #             await end_chat("riders", user.id, "vendors", vendor.user_id)
# #             await subscribe_to_riders_location("unsubscribe", user.id, order.user_id)
# #         except Exception as e:
# #             logger.warning(f"Chat cleanup error: {str(e)}")

# #         return translate({
# #             "status": "delivered",
# #             "order_id": order_id,
# #             "is_on_time": order.is_on_time,
# #             "payout": float(order.base_rate or 0) + float(order.distance_bonus or 0)
# #         }, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error marking delivered: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.post("/orders/cancel/{order_id}/")
# # async def cancel_order(
# #     request: Request,
# #     order_id: str,
# #     reason: Optional[str] = Form(None),
# #     user: User = Depends(get_current_user),
# #     redis=Depends(get_redis)
# # ):
# #     """
# #     Cancel an order.
# #     Cannot cancel if already delivered or previously cancelled.
# #     Restores item stock.
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         order_item = await OrderItem.get_or_none(order=order)
# #         if not order_item:
# #             raise HTTPException(status_code=404, detail="Order item not found")

# #         item = await Item.get_or_none(id=order_item.item_id)
# #         if not item:
# #             raise HTTPException(status_code=404, detail="Item not found")

# #         vendor = await VendorProfile.get_or_none(id=item.vendor_id)
# #         if not vendor:
# #             raise HTTPException(status_code=404, detail="Vendor not found")

# #         # Cannot cancel if already delivered or cancelled
# #         if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
# #             raise HTTPException(status_code=400, detail="Order cannot be cancelled")

# #         order.status = OrderStatus.CANCELLED
# #         order.cancel_reason = reason
# #         order.cancelled_at = datetime.utcnow()
# #         await order.save()

# #         # Restore stock
# #         item.stock += order_item.quantity
# #         await item.save()

# #         notify_payload = {
# #             "type": "order_cancelled",
# #             "order_id": order_id,
# #             "cancelled_at": datetime.utcnow().isoformat(),
# #             "reason": reason
# #         }

# #         await redis.publish("order_updates", json.dumps(notify_payload))

# #         try:
# #             await manager.send_notification(
# #                 "customers",
# #                 str(order.user_id),
# #                 "Order Cancelled",
# #                 f"Reason: {reason or 'Not specified'}"
# #             )
# #             await manager.send_notification(
# #                 "vendors",
# #                 str(vendor.user_id),
# #                 "Order Cancelled",
# #                 f"Order {order_id} has been cancelled"
# #             )
# #             await send_notification(order.user_id, "Order Cancelled", f"Reason: {reason or 'Not specified'}")
# #         except Exception as e:
# #             logger.warning(f"Cancellation notification error: {str(e)}")

# #         try:
# #             rider = await RiderProfile.get_or_none(id=order.rider_id)
# #             if rider:
# #                 await end_chat("riders", rider.user_id, "customers", order.user_id)
# #                 await end_chat("riders", rider.user_id, "vendors", vendor.user_id)
# #                 await subscribe_to_riders_location("unsubscribe", rider.user_id, order.user_id)
# #         except Exception as e:
# #             logger.warning(f"Chat cleanup error: {str(e)}")

# #         return translate({"status": "cancelled", "order_id": order_id}, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error cancelling order: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.get("/orders/{order_id}/")
# # async def get_order_details(
# #     request: Request,
# #     order_id: str,
# #     user: User = Depends(get_current_user),
# # ):
# #     """
# #     Get detailed information about an order.
# #     Includes rider, vendor, customer, payout, and delivery status.
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         order = await Order.get_or_none(id=order_id)
# #         if not order:
# #             raise HTTPException(status_code=404, detail="Order not found")

# #         # rider = None
# #         # rider_name = None
# #         # if order.rider_id:
# #         #     rider = await RiderProfile.get_or_none(id=order.rider_id)
# #         #     if rider and rider.user:
# #         #         rider_name = rider.user.name

# #         # order_item = await OrderItem.get_or_none(order=order)
# #         # if not order_item:
# #         #     raise HTTPException(status_code=404, detail="Order item not found")

# #         # item = await Item.get_or_none(id=order_item.item_id)
# #         # if not item:
# #         #     raise HTTPException(status_code=404, detail="Item not found")

# #         # vendor = await VendorProfile.get_or_none(id=item.vendor_id)
# #         # if not vendor:
# #         #     raise HTTPException(status_code=404, detail="Vendor not found")
        

# #         return await OrderOut.from_tortoise_orm(translate(order, lang))

# #         # return translate({
# #         #     "id": order.id,
# #         #     "status": str(order.status),
# #         #     "delivery_type": str(order.delivery_type),
# #         #     "rider_id": rider.user_id if rider else None,
# #         #     "rider_name": rider_name,
# #         #     "vendor_id": vendor.user_id,
# #         #     "customer_id": order.user_id,
# #         #     "base_rate": float(order.base_rate or 0),
# #         #     "distance_bonus": float(order.distance_bonus or 0),
# #         #     "total_payout": float((order.base_rate or 0) + (order.distance_bonus or 0)),
# #         #     "eta_minutes": order.eta_minutes,
# #         #     "is_on_time": order.is_on_time,
# #         #     "is_combined": order.is_combined,
# #         #     "combined_pickups": order.combined_pickups,
# #         #     "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
# #         #     "completed_at": order.completed_at.isoformat() if order.completed_at else None
# #         # }, lang)

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error getting order details: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # @router.get("/orders/")
# # async def list_orders(
# #     request: Request,
# #     skip: int = Query(default=0),
# #     limit: int = Query(default=10),
# #     user: User = Depends(get_current_user),
# # ):
# #     """
# #     List orders assigned to the current rider.
# #     Supports pagination with skip and limit.
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         rider = await RiderProfile.get_or_none(user=user)
# #         if not rider:
# #             raise HTTPException(status_code=403, detail="Not a rider")

# #         orders = await Order.filter(
# #             rider=rider
# #         ).offset(skip).limit(limit).order_by("-created_at").all()



# #         return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error listing orders: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    

# # @router.get("/current-orders/")
# # async def current_orders_list(
# #     request: Request,
# #     skip: int = Query(default=0),
# #     limit: int = Query(default=10),
# #     user: User = Depends(get_current_user),
# # ):
# #     """
# #     List orders assigned to the current rider.
# #     Supports pagination with skip and limit.
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         rider = await RiderProfile.get_or_none(user=user)
# #         if not rider:
# #             raise HTTPException(status_code=403, detail="Not a rider")

# #         orders = await Order.filter(
# #             rider=rider, status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
# #         ).offset(skip).limit(limit).order_by("-created_at").all()



# #         return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error listing orders: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    




# # @router.get("/offered-orders/")
# # async def list_orders_offer(
# #     request: Request,
# #     skip: int = Query(default=0),
# #     limit: int = Query(default=10),
# #     user: User = Depends(get_current_user),
# # ):
# #     """
# #     List orders assigned to the current rider.
# #     Supports pagination with skip and limit.
# #     """
# #     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
# #     try:
# #         rider = await RiderProfile.get_or_none(user=user)
# #         if not rider:
# #             raise HTTPException(status_code=403, detail="Not a rider")

# #         orders = await Order.filter(
# #             rider=None, metadata__contains={"candidate_riders": [rider.id]}, status=OrderStatus.CONFIRMED
# #         ).offset(skip).limit(limit).order_by("-created_at").all()



# #         return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         logger.error(f"Error listing orders: {str(e)}")
# #         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")







# # from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Query, Request
# # from datetime import datetime, date, timedelta, timezone
# # from decimal import Decimal
# # from pydantic import BaseModel
# # from typing import Optional, List, Dict, Tuple
# # import logging
# # import json
# # import asyncio

# # from applications.user.models import User
# # from applications.user.rider import (
# #     RiderProfile, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses, OrderOffer
# # )
# # from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
# # from applications.items.models import Item, ItemCategory
# # from applications.user.vendor import VendorProfile
# # from applications.user.customer import CustomerProfile
# # from applications.earning.vendor_earning import add_money_to_vendor_account
# # from tortoise.contrib.pydantic import pydantic_model_creator
# # from app.token import get_current_user
# # from app.utils.geo import haversine, bbox_for_radius, estimate_eta
# # from app.utils.websocket_manager import manager
# # from app.redis import get_redis
# # from tortoise.transactions import in_transaction
# # from tortoise.exceptions import IntegrityError
# # from .notifications import send_notification
# # from .websocket_endpoints import start_chat, end_chat, subscribe_to_riders_location
# # from app.utils.translator import translate

# # # ============================================================================
# # # CONFIGURATION & LOGGING
# # # ============================================================================

# # logger = logging.getLogger(__name__)

# # router = APIRouter(tags=['Rider Orders'])

# # Constants





























# OFFER_TIMEOUT_SECONDS = 1200  # 20 minutes total offer validity
# URGENT_OFFER_TIMEOUT = 60  # 1 minute per rider for urgent orders
# SPLIT_BROADCAST_TIMEOUT = 60  # 1 minute to accept for split/combined
# GEO_REDIS_KEY = "riders_geo"
# INITIAL_RADIUS_KM = 3.0
# RADIUS_STEP_KM = 1.0
# MAX_RADIUS_KM = 20.0
# URGENT_RADIUS_KM = 10.0

# # Delivery Fee Configuration
# DELIVERY_FEES = {
#     "combined": {"base": 40, "per_km": 2},
#     "split": {"base": 60, "per_km": 3},
#     "urgent": {"base": 80, "per_km": 4}
# }

# # ============================================================================
# # PYDANTIC MODELS
# # ============================================================================

# OrderOut = pydantic_model_creator(Order, name='OrderOut')

# class OrderRejectRequest(BaseModel):
#     """Rejection request with reason"""
#     order_id: str
#     reason: str

# class RiderStatsResponse(BaseModel):
#     """Rider statistics for tracking rejections"""
#     total_offers: int
#     rejections: int
#     timeout_rejections: int
#     acceptance_rate: float

# class OrderOfferResponse(BaseModel):
#     """Order offer response for rider"""
#     order_id: str
#     delivery_type: str
#     payout: float
#     distance_km: float
#     estimated_time_minutes: int
#     is_urgent: bool
#     created_at: datetime

# # ============================================================================
# # HELPER FUNCTIONS
# # ============================================================================

# @router.get("/test/")
# async def test_endpoint():
#     return {"status": "Rider Orders API is operational"}

# def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
#     """Convert datetime to UTC if not already"""
#     if dt is None:
#         return None
#     if dt.tzinfo is None:
#         return dt.replace(tzinfo=timezone.utc)
#     return dt.astimezone(timezone.utc)

# async def categorize_order_items(
#     items: List[OrderItem]
# ) -> Dict[str, List[OrderItem]]:
#     """
#     Categorize order items by type (FOOD, GROCERY, MEDICINE).
#     Returns: {category_type: [items]}
#     """
#     categorized = {"FOOD": [], "GROCERY": [], "MEDICINE": []}
    
#     for item in items:
#         item_obj = await Item.get_or_none(id=item.item_id)
#         if item_obj:
#             # Determine category from item or vendor type
#             category = getattr(item_obj, 'category', 'GROCERY')
#             if category not in categorized:
#                 category = 'GROCERY'
#             categorized[category].append(item)
    
#     return categorized

# async def group_items_by_vendor(
#     categorized_items: Dict[str, List[OrderItem]]
# ) -> Dict[str, Tuple[str, List[OrderItem]]]:
#     """
#     Group items by vendor source.
#     Returns: {vendor_id: (category_type, items)}
#     """
#     vendor_groups = {}
    
#     for category, items in categorized_items.items():
#         for item in items:
#             item_obj = await Item.get_or_none(id=item.item_id)
#             if item_obj:
#                 vendor_id = str(item_obj.vendor_id)
#                 if vendor_id not in vendor_groups:
#                     vendor_groups[vendor_id] = (category, [])
#                 vendor_groups[vendor_id][1].append(item)
    
#     return vendor_groups

# def calculate_delivery_fee(
#     delivery_type: str,
#     distance_km: float = 1.0
# ) -> Decimal:
#     """
#     Calculate delivery fee based on type and distance.
#     Returns: Decimal fee
#     """
#     delivery_type = delivery_type.lower()
#     config = DELIVERY_FEES.get(delivery_type, DELIVERY_FEES["combined"])
    
#     fee = config["base"] + (distance_km * config["per_km"])
#     return Decimal(str(fee))

# def determine_delivery_streams(
#     order_data: dict,
#     has_medicine: bool,
#     has_non_medicine: bool,
#     urgent_medicine: bool = False
# ) -> List[Dict]:
#     """
#     Determine fulfillment streams based on order composition and settings.
    
#     Rules:
#     - If urgent_medicine=True and medicine exists: 2 streams (medicine + others)
#     - If urgent_medicine=False: 1 stream (everything together)
#     - If split=True and has cross-category: split by category
    
#     Returns: List of stream configs
#     """
#     delivery_option = order_data.get("delivery_option", {})
#     delivery_type = delivery_option.get("type", "combined").lower()
    
#     streams = []
    
#     if not has_medicine:
#         # No medicine: single stream
#         streams.append({
#             "type": "food_grocery",
#             "delivery_type": delivery_type,
#             "items": order_data.get("items", []),
#             "is_urgent": False
#         })
#     elif delivery_type == "combined" and not urgent_medicine:
#         # Combined + no urgent: single stream
#         streams.append({
#             "type": "all",
#             "delivery_type": "combined",
#             "items": order_data.get("items", []),
#             "is_urgent": False
#         })
#     elif delivery_type == "combined" and urgent_medicine:
#         # Combined + urgent: 2 streams
#         medicine_items = [i for i in order_data.get("items", []) 
#                          if i.get("category") == "MEDICINE"]
#         other_items = [i for i in order_data.get("items", []) 
#                       if i.get("category") != "MEDICINE"]
        
#         streams.append({
#             "type": "medicine",
#             "delivery_type": "urgent",
#             "items": medicine_items,
#             "is_urgent": True
#         })
        
#         if other_items:
#             streams.append({
#                 "type": "food_grocery",
#                 "delivery_type": "combined",
#                 "items": other_items,
#                 "is_urgent": False
#             })
    
#     elif delivery_type == "split":
#         # Split: separate by category
#         food_items = [i for i in order_data.get("items", []) 
#                      if i.get("category") == "FOOD"]
#         grocery_items = [i for i in order_data.get("items", []) 
#                         if i.get("category") == "GROCERY"]
#         medicine_items = [i for i in order_data.get("items", []) 
#                          if i.get("category") == "MEDICINE"]
        
#         if medicine_items:
#             streams.append({
#                 "type": "medicine",
#                 "delivery_type": "urgent" if urgent_medicine else "split",
#                 "items": medicine_items,
#                 "is_urgent": urgent_medicine
#             })
        
#         if food_items:
#             streams.append({
#                 "type": "food",
#                 "delivery_type": "split",
#                 "items": food_items,
#                 "is_urgent": False
#             })
        
#         if grocery_items:
#             streams.append({
#                 "type": "grocery",
#                 "delivery_type": "split",
#                 "items": grocery_items,
#                 "is_urgent": False
#             })
    
#     return streams if streams else [{
#         "type": "all",
#         "delivery_type": delivery_type,
#         "items": order_data.get("items", []),
#         "is_urgent": False
#     }]

# async def notify_rider_websocket(
#     rider_id: int,
#     order: Order,
#     notification_type: str = "order_offer"
# ) -> bool:
#     """
#     Send WebSocket notification to rider.
#     Returns: True if successful, False otherwise
#     """
#     try:
#         payload = {
#             "type": notification_type,
#             "order_id": str(order.id),
#             "timestamp": datetime.utcnow().isoformat(),
#             "delivery_type": str(order.delivery_type),
#             "payout": float(order.base_rate + order.distance_bonus)
#         }
        
#         rider = await RiderProfile.get_or_none(id=rider_id)
#         if not rider:
#             logger.error(f"Rider {rider_id} not found for WebSocket notification")
#             return False
        
#         # Send via WebSocket manager
#         await manager.send_notification(
#             "riders",
#             str(rider.user_id),
#             "New Order Offer",
#             f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
#         )
        
#         logger.info(f"WebSocket notification sent to rider {rider_id} for order {order.id}")
#         return True
    
#     except Exception as e:
#         logger.error(f"WebSocket notification error for rider {rider_id}: {str(e)}")
#         return False

# async def notify_rider_pushnotification(
#     rider_id: int,
#     title: str,
#     body: str
# ) -> bool:
#     """
#     Send push notification to rider.
#     Returns: True if successful, False otherwise
#     """
#     try:
#         rider = await RiderProfile.get_or_none(id=rider_id)
#         if not rider or not rider.user_id:
#             logger.warning(f"Rider {rider_id} not found or no user_id for push notification")
#             return False
        
#         await send_notification(rider.user_id, title, body)
#         logger.info(f"Push notification sent to rider {rider_id}: {title}")
#         return True
    
#     except Exception as e:
#         logger.error(f"Push notification error for rider {rider_id}: {str(e)}")
#         return False

# async def find_candidate_riders(
#     vendor_lat: float,
#     vendor_lng: float,
#     is_urgent: bool = False,
#     top_n: int = 20,
#     redis=None
# ) -> List[RiderProfile]:
#     """
#     Find eligible rider candidates based on location and availability.
#     Strategy:
#     1. Try Redis GEO search
#     2. Fall back to database query
#     3. Expand radius progressively if needed
#     """
#     candidates = []
#     radius = URGENT_RADIUS_KM if is_urgent else INITIAL_RADIUS_KM
#     max_radius = URGENT_RADIUS_KM if is_urgent else MAX_RADIUS_KM
#     existing_ids = set()
    
#     while len(candidates) < top_n and radius <= max_radius:
#         candidate_rider_ids = []
        
#         # Try Redis GEO search
#         if redis:
#             try:
#                 geo_res = await redis.execute_command(
#                     "GEORADIUS",
#                     GEO_REDIS_KEY,
#                     vendor_lng,
#                     vendor_lat,
#                     radius,
#                     "km",
#                     "ASC",
#                     "COUNT",
#                     int(top_n * 3)
#                 )
                
#                 if geo_res:
#                     candidate_rider_ids = [
#                         int(x) for x in geo_res
#                         if int(x) not in existing_ids
#                     ]
            
#             except Exception as e:
#                 logger.warning(f"Redis GEORADIUS search failed: {str(e)}")
#                 candidate_rider_ids = []
        
#         # Get riders from database
#         try:
#             if candidate_rider_ids:
#                 riders = await RiderProfile.filter(
#                     id__in=candidate_rider_ids,
#                     is_available=True
#                 ).prefetch_related("current_location").all()
#             else:
#                 # Fallback: query all available riders
#                 riders = await RiderProfile.filter(
#                     is_available=True
#                 ).prefetch_related("current_location").all()
            
#             # Calculate distances and filter by radius
#             rider_distances = []
#             for r in riders:
#                 if r.id in existing_ids:
#                     continue
                
#                 loc = r.current_location
#                 if not loc:
#                     continue
                
#                 dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
#                 if dist <= radius:
#                     rider_distances.append((r, dist))
#                     existing_ids.add(r.id)
            
#             # Sort by distance and append
#             rider_distances.sort(key=lambda x: x[1])
#             candidates.extend(rider_distances)
        
#         except Exception as e:
#             logger.error(f"Database query error at radius {radius}km: {str(e)}")
        
#         radius += RADIUS_STEP_KM
    
#     # Remove duplicates and return top N
#     seen_ids = set()
#     result = []
#     for rider, _ in candidates:
#         if rider.id not in seen_ids:
#             result.append(rider)
#             seen_ids.add(rider.id)
#         if len(result) >= top_n:
#             break
    
#     logger.info(f"Found {len(result)} candidate riders (urgent={is_urgent})")
#     return result

# async def send_offer_to_rider(
#     order_id: str,
#     rider_id: int,
#     is_urgent: bool = False
# ) -> bool:
#     """
#     Send order offer to a single rider.
#     Creates OrderOffer record and sends notifications.
#     Returns: True if successful
#     """
#     try:
#         order = await Order.get_or_none(id=order_id)
#         rider = await RiderProfile.get_or_none(id=rider_id)
        
#         if not order or not rider:
#             logger.error(f"Order {order_id} or Rider {rider_id} not found")
#             return False
        
#         # Create OrderOffer record
#         offer = await OrderOffer.create(
#             order=order,
#             rider=rider,
#             status="PENDING",
#             is_urgent=is_urgent,
#             created_at=datetime.utcnow()
#         )

#         print(f"Offer created for rider {rider_id}, order {order_id}: {offer.id}")
        
#         # Send WebSocket notification
#         ws_success = await notify_rider_websocket(rider_id, order, "order_offer")
        
#         # Send push notification
#         is_urgent_order = order.delivery_type == DeliveryTypeEnum.URGENT
#         notification_title = "🚨 URGENT: Medicine Delivery" if is_urgent_order else "New Order Offer"
#         notification_body = f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
        
#         push_success = await notify_rider_pushnotification(rider_id, notification_title, notification_body)
        
#         logger.info(f"Offer {offer.id} created for rider {rider_id}, order {order_id}")
#         return True
    
#     except Exception as e:
#         logger.error(f"Error sending offer to rider {rider_id}: {str(e)}")
#         return False

# async def offer_order_broadcast(
#     order_id: str,
#     candidates: List[RiderProfile],
#     background_tasks: BackgroundTasks
# ) -> None:
#     """
#     Broadcast order offer to multiple riders simultaneously (COMBINED/SPLIT).
#     First to accept gets the order.
#     """
#     try:
#         logger.info(f"Broadcasting order {order_id} to {len(candidates)} riders")
        
#         # Send offers to all riders in parallel
#         tasks = [
#             send_offer_to_rider(order_id, rider.id, is_urgent=False)
#             for rider in candidates
#         ]
        
#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         success_count = sum(1 for r in results if r is True)
        
#         logger.info(f"Broadcast sent to {success_count}/{len(candidates)} riders for order {order_id}")
    
#     except Exception as e:
#         logger.error(f"Error in broadcast offering: {str(e)}")

# async def offer_order_sequentially(
#     order_id: str,
#     candidates: List[RiderProfile],
#     background_tasks: BackgroundTasks,
#     timeout_per_rider: int = URGENT_OFFER_TIMEOUT
# ) -> None:
#     """
#     Offer order to riders sequentially (URGENT orders).
#     Wait timeout before moving to next rider.
#     """
#     try:
#         logger.info(f"Sequentially offering order {order_id} to {len(candidates)} riders (timeout={timeout_per_rider}s)")
        
#         for idx, rider in enumerate(candidates):
#             # Send offer
#             sent = await send_offer_to_rider(order_id, rider.id, is_urgent=True)
            
#             if sent:
#                 logger.info(f"Urgent offer {idx+1}/{len(candidates)} sent to rider {rider.id}")
                
#                 # Wait before moving to next rider
#                 await asyncio.sleep(timeout_per_rider)
                
#                 # Check if order was accepted
#                 order = await Order.get_or_none(id=order_id)
#                 if order and order.rider_id:
#                     logger.info(f"Order {order_id} accepted by rider {order.rider_id}, stopping sequential offers")
#                     break
    
#     except Exception as e:
#         logger.error(f"Error in sequential offering: {str(e)}")

# # # ============================================================================
# # # VENDOR FLOW: Create Vendor Offers (after payment confirmation)
# # # ============================================================================

# @router.post("/vendor/create-offer/{parent_order_id}/")
# async def create_vendor_offers(
#     request: Request,
#     parent_order_id: str,
#     background_tasks: BackgroundTasks,
#     prepare_time: int = Query(30, ge=5, le=180),
#     top_n: int = Query(20, ge=1, le=50),
#     vendor: User = Depends(get_current_user),
#     redis=Depends(get_redis)
# ):
#     """
#     VENDOR ENDPOINT: Create order offers after order is placed and payment confirmed.
    
#     Flow:
#     1. Fetch all orders with this parent_order_id (grouped by vendor)
#     2. Vendor can only create offers for their own orders
#     3. For each order: determine delivery streams (urgent vs normal)
#     4. For each stream: find candidate riders
#     5. Broadcast/sequential offer based on stream type
#     6. Update order metadata with offer info
    
#     Note: place_order endpoint is NOT changed - input/output same
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Get vendor profile
#         vendor_profile = await VendorProfile.get_or_none(user=vendor)
#         if not vendor_profile:
#             raise HTTPException(status_code=403, detail="Not a vendor")
        
#         # Fetch all orders for this parent_order_id
#         orders = await Order.filter(
#             parent_order_id=parent_order_id
#         ).prefetch_related("items__item").all()
        
#         if not orders:
#             raise HTTPException(status_code=404, detail="No orders found for this parent order")
        
#         #print(f"Vendor {vendor.id} creating offers for parent order {parent_order_id}, total orders: {len(orders)}")
        
#         # Filter orders for this vendor only
#         vendor_orders = [o for o in orders if o.vendor_id == vendor.id]
#         if not vendor_orders:
#             raise HTTPException(status_code=403, detail="No orders for this vendor")
        
#         #print(f"Vendor {vendor.id} has {len(vendor_orders)} order(s) to process for offers")
        
#         # Process each vendor's orders
#         processed_orders = []
        
#         for order in vendor_orders:
#             order_items = await OrderItem.filter(order=order).all()
#             if not order_items:
#                 continue

#             #print(f"Processing order {order.id} with {len(order_items)} item(s)")
            
#             # Categorize items
#             # has_medicine = any(
#             #     (await Item.get_or_none(id=item.item_id)).category == "MEDICINE" 
#             #     for item in order_items
#             # )
#             # print(f"has_medicine: {has_medicine}")
#             # has_non_medicine = any(
#             #     (await Item.get_or_none(id=item.item_id)).category != "MEDICINE" 
#             #     for item in order_items
#             # )

#             item_ids = [oi.item_id for oi in order_items]

#             # single DB query
#             items = await Item.filter(id__in=item_ids).all()   # returns list of Item objects

#             # make a dict for O(1) lookup (optional)
#             categories = {itm.id: itm.category for itm in items}

#             # check flags safely (handle missing items)
#             has_medicine = any(categories.get(iid) == "MEDICINE" for iid in item_ids)
#             print(f"has_medicine: {has_medicine}")
#             has_non_medicine = any(categories.get(iid) and categories.get(iid) != "MEDICINE" for iid in item_ids)
#             print(f"has_non_medicine: {has_non_medicine}")
            
#             # Check if urgent medicine was selected
#             urgent_medicine = (
#                 order.delivery_type == DeliveryTypeEnum.URGENT and has_medicine
#             )
#             print(f"before")
#             # Determine delivery streams
#             streams = determine_delivery_streams(
#                 {
#                     "items": [{"id": i.item_id, "category": "MEDICINE"} for i in order_items],
#                     "delivery_option": {"type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type}
#                 },
#                 has_medicine=has_medicine,
#                 has_non_medicine=has_non_medicine,
#                 urgent_medicine=urgent_medicine
#             )
            
#             logger.info(f"Order {order.id} has {len(streams)} stream(s): {[s['type'] for s in streams]}")
            
#             # For each stream, find riders
#             for stream_idx, stream in enumerate(streams):
#                 stream_type = stream["type"]
#                 is_urgent = stream["is_urgent"]
#                 delivery_type = stream["delivery_type"]
                
#                 # Find candidate riders
#                 vendor_location = vendor_profile
#                 candidates = await find_candidate_riders(
#                     vendor_location.latitude,
#                     vendor_location.longitude,
#                     is_urgent=is_urgent,
#                     top_n=top_n,
#                     redis=redis
#                 )
                
#                 if not candidates:
#                     logger.warning(f"No riders available for order {order.id} stream {stream_idx}")
#                     continue
                
#                 # Update order metadata
#                 order.status = OrderStatus.CONFIRMED
#                 order.metadata = order.metadata or {}
#                 order.metadata["streams"] = order.metadata.get("streams", [])
#                 order.metadata["streams"].append({
#                     "stream_type": stream_type,
#                     "is_urgent": is_urgent,
#                     "candidate_riders": [r.id for r in candidates],
#                     "offered_at": datetime.utcnow().isoformat()
#                 })
#                 order.prepare_time = prepare_time
#                 await order.save()
                
#                 # Offer to riders based on stream type
#                 if is_urgent:
#                     # Sequential for urgent
#                     background_tasks.add_task(
#                         offer_order_sequentially,
#                         order.id,
#                         candidates,
#                         background_tasks
#                     )
#                 else:
#                     # Broadcast for combined/split
#                     background_tasks.add_task(
#                         offer_order_broadcast,
#                         order.id,
#                         candidates,
#                         background_tasks
#                     )
                
#                 processed_orders.append({
#                     "order_id": order.id,
#                     "stream_type": stream_type,
#                     "delivery_type": delivery_type,
#                     "is_urgent": is_urgent,
#                     "candidate_count": len(candidates)
#                 })
        
#         return translate({
#             "success": True,
#             "message": f"Offers created for {len(processed_orders)} order stream(s)",
#             "data": {
#                 "parent_order_id": parent_order_id,
#                 "processed_orders": processed_orders,
#                 "total_streams": sum(len(o.get("streams", [])) for o in [{"streams": []}])
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error creating vendor offers: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# # # ============================================================================
# # # RIDER FLOW: Accept/Reject Orders
# # # ============================================================================

# @router.post("/orders/accept/{order_id}/")
# async def accept_order(
#     request: Request,
#     order_id: str,
#     user: User = Depends(get_current_user),
#     redis=Depends(get_redis),
#     background_tasks: BackgroundTasks = BackgroundTasks()
# ):
#     """
#     RIDER accepts an order.
    
#     Flow:
#     1. Claim order via Redis (prevent race condition)
#     2. Validate order status
#     3. Update order with rider assignment
#     4. Mark offer as ACCEPTED
#     5. Reject all other pending offers for this order
#     6. Send notifications
#     7. Start chat channels
    
#     Restrictions:
#     - URGENT/SPLIT: Cannot accept another order until delivered
#     - COMBINED: Can accept other orders
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Get rider profile
#         rider_profile = await RiderProfile.get_or_none(user=user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider profile")
        
#         # Use Redis to prevent race condition
#         claim_key = f"order_claim:{order_id}"
#         claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)
        
#         if not claimed:
#             raise HTTPException(status_code=400, detail="Order already claimed by another rider")
        
#         # Get order
#         order = await Order.get_or_none(id=order_id).prefetch_related(
#             "user", "vendor", "items__item"
#         )
        
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Validate order status
#         if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING]:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot accept order with status: {order.status.value if hasattr(order.status, 'value') else order.status}"
#             )
        
#         # Check delivery restrictions
#         if order.delivery_type in [DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT]:
#             # Cannot have another active order
#             active_orders = await Order.filter(
#                 rider=rider_profile,
#                 status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.PREPARED, OrderStatus.OUT_FOR_DELIVERY]
#             ).count()
            
#             if active_orders > 0:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Rider has active urgent/split order. Cannot accept another."
#                 )
        
#         # Assign rider
#         order.rider = rider_profile
#         order.status = OrderStatus.PROCESSING
#         order.accepted_at = datetime.utcnow()
        
#         # Calculate payout
#         vendor = await VendorProfile.get_or_none(id=order.vendor_id)
#         if vendor and rider_profile.current_location:
#             distance = haversine(
#                 vendor.latitude,
#                 vendor.longitude,
#                 rider_profile.current_location.latitude,
#                 rider_profile.current_location.longitude
#             )
            
#             order.pickup_distance_km = distance
            
#             # Calculate based on delivery type
#             delivery_type = order.delivery_type.value if hasattr(order.delivery_type, 'value') else str(order.delivery_type)
#             fee = calculate_delivery_fee(delivery_type, distance)
            
#             order.base_rate = Decimal(str(fee))
        
#         await order.save()
        
#         # Mark this offer as accepted
#         offer = await OrderOffer.get_or_none(order=order, rider=rider_profile)
#         if offer:
#             offer.status = "ACCEPTED"
#             offer.accepted_at = datetime.utcnow()
#             await offer.save()
        
#         # Reject all other offers for this order
#         other_offers = await OrderOffer.filter(order=order).exclude(rider=rider_profile)
#         for other_offer in other_offers:
#             if other_offer.status == "PENDING":
#                 other_offer.status = "REJECTED"
#                 other_offer.rejected_at = datetime.utcnow()
#                 await other_offer.save()
        
#         # Send notifications
#         try:
#             # Notify customer
#             await send_notification(
#                 order.user.id,
#                 "Rider Assigned",
#                 f"Rider assigned to your order #{order.id}"
#             )
            
#             # Notify vendor
#             vendor_user = await User.get_or_none(id=order.vendor_id)
#             if vendor_user:
#                 await send_notification(
#                     vendor_user.id,
#                     "Order Accepted",
#                     f"Rider accepted order #{order.id}"
#                 )
        
#         except Exception as e:
#             logger.warning(f"Notification error: {str(e)}")
        
#         # Start chat channels
#         try:
#             await start_chat(user.id, order.user.id, order.id)
#         except Exception as e:
#             logger.warning(f"Chat initialization error: {str(e)}")
        
#         return translate({
#             "success": True,
#             "message": "Order accepted successfully",
#             "data": {
#                 "order_id": order.id,
#                 "rider_id": rider_profile.id,
#                 "payout": float(order.base_rate),
#                 "distance_km": order.pickup_distance_km,
#                 "status": order.status.value if hasattr(order.status, 'value') else str(order.status)
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error accepting order: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# @router.post("/orders/reject/{order_id}/")
# async def reject_order(
#     request: Request,
#     order_id: str,
#     reject_data: OrderRejectRequest,
#     user: User = Depends(get_current_user),
#     redis=Depends(get_redis)
# ):
#     """
#     RIDER rejects an order offer.
    
#     Flow:
#     1. Validate order exists
#     2. Mark offer as REJECTED
#     3. Record rejection (for rider stats)
#     4. If other offers exist, order remains available
#     5. If no offers, order goes back to pending
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         rider_profile = await RiderProfile.get_or_none(user=user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider")
        
#         # Get order
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Get and update offer
#         offer = await OrderOffer.get_or_none(order=order, rider=rider_profile)
#         if not offer:
#             raise HTTPException(status_code=404, detail="Offer not found")
        
#         offer.status = "REJECTED"
#         offer.rejected_at = datetime.utcnow()
#         offer.rejection_reason = reject_data.reason
#         await offer.save()
        
#         # Update rider stats
#         work_day = await WorkDay.get_or_none(
#             rider=rider_profile,
#             date=date.today()
#         )
        
#         if work_day:
#             work_day.rejection_count += 1
#             await work_day.save()
        
#         # Check if order should be removed from rider home
#         pending_offers = await OrderOffer.filter(
#             order=order,
#             status="PENDING"
#         ).count()
        
#         # Order will disappear from rider list if no pending offers exist for them
#         logger.info(f"Order {order_id} rejected by rider {rider_profile.id}. Pending offers: {pending_offers}")
        
#         return translate({
#             "success": True,
#             "message": "Order rejected successfully",
#             "data": {
#                 "order_id": order_id,
#                 "pending_offers": pending_offers
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error rejecting order: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# # # ============================================================================
# # # RIDER HOME PAGE: Get Available Offers
# # # ============================================================================

# @router.get("/orders/offers/")
# async def get_available_orders(
#     request: Request,
#     user: User = Depends(get_current_user),
#     redis=Depends(get_redis)
# ):
#     """
#     Get list of available order offers for rider (home page).
    
#     Filter:
#     - PENDING offers only
#     - Exclude if rider already has active order (for URGENT/SPLIT)
#     - Show payout, distance, delivery type
    
#     After reject/timeout: offer disappears from list
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         rider_profile = await RiderProfile.get_or_none(user=user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider")
        
#         # Get pending offers for this rider
#         pending_offers = await OrderOffer.filter(
#             rider=rider_profile,
#             status="PENDING"
#         ).prefetch_related("order__vendor", "order__user").all()
        
#         # Filter out if rider has active orders (for URGENT/SPLIT)
#         available_offers = []
        
#         for offer in pending_offers:
#             order = offer.order
            
#             # Check if offer has timed out
#             if order.expires_at and datetime.utcnow() > order.expires_at:
#                 # Mark as expired
#                 offer.status = "TIMEOUT"
#                 await offer.save()
#                 continue
            
#             # Check if order already accepted by another rider
#             if order.rider_id and order.rider_id != rider_profile.id:
#                 offer.status = "REJECTED"
#                 await offer.save()
#                 continue
            
#             # Check delivery restrictions
#             if order.delivery_type in [DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT]:
#                 active_orders = await Order.filter(
#                     rider=rider_profile,
#                     status__in=[
#                         OrderStatus.CONFIRMED,
#                         OrderStatus.SHIPPED,
#                         OrderStatus.PREPARED,
#                         OrderStatus.OUT_FOR_DELIVERY
#                     ]
#                 ).count()
                
#                 if active_orders > 0:
#                     continue  # Skip this offer
            
#             available_offers.append({
#                 "order_id": order.id,
#                 "delivery_type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type,
#                 "payout": float(order.base_rate + order.distance_bonus if order.distance_bonus else order.base_rate),
#                 "distance_km": float(order.pickup_distance_km) if order.pickup_distance_km else 0,
#                 "estimated_time_minutes": order.eta_minutes or 15,
#                 "is_urgent": order.delivery_type == DeliveryTypeEnum.URGENT,
#                 "customer_name": order.user.name if order.user else "Unknown",
#                 "vendor_name": order.vendor.name if order.vendor else "Unknown",
#                 "created_at": order.offered_at.isoformat() if order.offered_at else None,
#                 "expires_at": order.expires_at.isoformat() if order.expires_at else None
#             })
        
#         return translate({
#             "success": True,
#             "message": f"Found {len(available_offers)} available orders",
#             "data": {
#                 "total_offers": len(available_offers),
#                 "offers": available_offers
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error fetching available orders: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# # # ============================================================================
# # # ORDER STATUS UPDATES (Existing Flow - No Changes)
# # # ============================================================================

# @router.patch("/orders/{order_id}/status/")
# async def update_order_status(
#     request: Request,
#     order_id: str,
#     new_status: str,
#     user: User = Depends(get_current_user)
# ):
#     """
#     Update order status (vendor or rider can update).
    
#     Status flow remains the same:
#     PENDING → CONFIRMED → PROCESSING → PREPARED → SHIPPED → OUT_FOR_DELIVERY → DELIVERED
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         order = await Order.get_or_none(id=order_id).prefetch_related("vendor", "rider")
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Check authorization
#         vendor = await VendorProfile.get_or_none(user=user)
#         rider = await RiderProfile.get_or_none(user=user)
        
#         is_vendor = vendor and order.vendor_id == user.id
#         is_rider = rider and order.rider_id == rider.id
        
#         if not (is_vendor or is_rider or user.is_staff):
#             raise HTTPException(status_code=403, detail="Not authorized")
        
#         # Update status
#         try:
#             order.status = OrderStatus(new_status)
#             order.updated_at = datetime.utcnow()
            
#             if new_status == "delivered":
#                 order.completed_at = datetime.utcnow()
            
#             await order.save()
        
#         except ValueError:
#             raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
        
#         return translate({
#             "success": True,
#             "message": f"Order status updated to {new_status}",
#             "data": {"order_id": order_id, "status": new_status}
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error updating order status: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")



from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Query, Request, status
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pydantic import BaseModel
from typing import Optional, List, Dict, Tuple, Any
import logging
import json
import asyncio
import uuid

from applications.user.models import User
from applications.user.rider import (
    RiderProfile, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses, OrderOffer
)
from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
from applications.items.models import Item
from applications.user.vendor import VendorProfile
from applications.user.customer import CustomerProfile
from applications.earning.vendor_earning import add_money_to_vendor_account
from tortoise.contrib.pydantic import pydantic_model_creator
from app.token import get_current_user
from app.utils.geo import haversine, bbox_for_radius, estimate_eta
from app.utils.websocket_manager import manager
from app.redis import get_redis
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError
from .notifications import send_notification
from .websocket_endpoints import start_chat, end_chat, subscribe_to_riders_location
from app.utils.translator import translate

# ============================================================================
# CONFIGURATION & LOGGING
# ============================================================================

logger = logging.getLogger(__name__)
router = APIRouter(tags=['Order Management'])

# Constants
OFFER_TIMEOUT_SECONDS = 1200  # 20 minutes total offer validity
URGENT_OFFER_TIMEOUT = 60  # 1 minute per rider for urgent orders
SPLIT_BROADCAST_TIMEOUT = 60  # 1 minute to accept for split/combined
GEO_REDIS_KEY = "riders_geo"
INITIAL_RADIUS_KM = 3.0
RADIUS_STEP_KM = 1.0
MAX_RADIUS_KM = 20.0
URGENT_RADIUS_KM = 10.0

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

OrderOut = pydantic_model_creator(Order, name='OrderOut')
class OrderRejectRequest(BaseModel):
    """Rejection request with reason"""
    order_id: str
    reason: str

class RiderStatsResponse(BaseModel):
    """Rider statistics for tracking rejections"""
    total_offers: int
    rejections: int
    timeout_rejections: int
    acceptance_rate: float

class CancelOrderRequest(BaseModel):
    """Request to cancel an order"""
    reason: Optional[str] = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
#     """Convert datetime to UTC if not already"""
#     if dt is None:
#         return None
#     if dt.tzinfo is None:
#         return dt.replace(tzinfo=timezone.utc)
#     return dt.astimezone(timezone.utc)

# async def notify_rider_websocket(
#     rider_id: int,
#     order: Order,
#     notification_type: str = "order_offer"
# ) -> bool:
#     """Send WebSocket notification to rider."""
#     try:
#         rider = await RiderProfile.get_or_none(id=rider_id)
#         if not rider:
#             logger.error(f"Rider {rider_id} not found for WebSocket notification")
#             return False
        
#         payload = {
#             "type": notification_type,
#             "order_id": str(order.id),
#             "timestamp": datetime.utcnow().isoformat(),
#             "delivery_type": str(order.delivery_type)
#         }
        
#         await manager.send_notification(
#             "riders",
#             str(rider.user_id),
#             "New Order Offer",
#             f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
#         )
#         logger.info(f"WebSocket notification sent to rider {rider_id} for order {order.id}")
#         return True
#     except Exception as e:
#         logger.error(f"WebSocket notification error for rider {rider_id}: {str(e)}")
#         return False

# async def notify_rider_pushnotification(
#     rider_id: int,
#     title: str,
#     body: str
# ) -> bool:
#     """Send push notification to rider."""
#     try:
#         rider = await RiderProfile.get_or_none(id=rider_id)
#         if not rider or not rider.user_id:
#             logger.warning(f"Rider {rider_id} not found or no user_id for push notification")
#             return False
        
#         await send_notification(rider.user_id, title, body)
#         logger.info(f"Push notification sent to rider {rider_id}: {title}")
#         return True
#     except Exception as e:
#         logger.error(f"Push notification error for rider {rider_id}: {str(e)}")
#         return False

# def calculate_delivery_fee(delivery_type: str, distance_km: float, base_fee: Decimal = None) -> Decimal:
#     """Calculate delivery fee based on type and distance"""
#     if base_fee is None:
#         base_fee = Decimal("44.00")
    
#     # Different fee structures by delivery type
#     fee_structure = {
#         "urgent": Decimal("75.00"),      # Premium for urgent
#         "combined": Decimal("44.00"),    # Standard for combined (splits cost)
#         "split": Decimal("50.00"),       # Slightly higher for individual rider
#     }
    
#     base = fee_structure.get(delivery_type.lower(), base_fee)
#     distance_bonus = Decimal(str(distance_km)) * Decimal("1.00")  # ₹1 per km
    
#     return base + distance_bonus

# def determine_delivery_streams(
#     order_data: Dict[str, Any],
#     has_medicine: bool = False,
#     has_non_medicine: bool = False,
#     urgent_medicine: bool = False
# ) -> List[Dict[str, Any]]:
#     """
#     Determine delivery streams based on order type and items.
    
#     Returns list of streams, each with type (urgent/combined/split) and metadata.
#     """
#     delivery_type = order_data.get("delivery_option", {}).get("type", "combined")
#     streams = []
    
#     if delivery_type == "urgent" and urgent_medicine:
#         # URGENT MEDICINE: Send immediately as urgent
#         streams.append({
#             "type": "urgent_medicine",
#             "is_urgent": True,
#             "delivery_type": "urgent",
#             "items_filter": lambda item: item.get("category") == "MEDICINE"
#         })
        
#         # Non-medicine items (if any) with normal delivery
#         if has_non_medicine:
#             streams.append({
#                 "type": "normal",
#                 "is_urgent": False,
#                 "delivery_type": "combined",
#                 "items_filter": lambda item: item.get("category") != "MEDICINE"
#             })
    
#     elif delivery_type == "combined":
#         # COMBINED: Keep together (but check for urgent medicine)
#         if urgent_medicine:
#             streams.append({
#                 "type": "urgent_medicine",
#                 "is_urgent": True,
#                 "delivery_type": "urgent",
#                 "items_filter": lambda item: item.get("category") == "MEDICINE"
#             })
#             streams.append({
#                 "type": "combined_non_urgent",
#                 "is_urgent": False,
#                 "delivery_type": "combined",
#                 "items_filter": lambda item: item.get("category") != "MEDICINE"
#             })
#         else:
#             streams.append({
#                 "type": "combined",
#                 "is_urgent": False,
#                 "delivery_type": "combined",
#                 "items_filter": lambda item: True
#             })
    
#     else:  # split
#         # SPLIT: Each order separate
#         if urgent_medicine:
#             streams.append({
#                 "type": "urgent_medicine",
#                 "is_urgent": True,
#                 "delivery_type": "urgent",
#                 "items_filter": lambda item: item.get("category") == "MEDICINE"
#             })
#         streams.append({
#             "type": "split",
#             "is_urgent": False,
#             "delivery_type": "split",
#             "items_filter": lambda item: item.get("category") != "MEDICINE" or delivery_type != "urgent"
#         })
    
#     return streams if streams else [{
#         "type": delivery_type,
#         "is_urgent": delivery_type == "urgent",
#         "delivery_type": delivery_type,
#         "items_filter": lambda item: True
#     }]

# async def find_candidate_riders(
#     vendor_lat: float,
#     vendor_lng: float,
#     is_urgent: bool = False,
#     top_n: int = 20,
#     redis=None,
#     exclude_rider_id: int = None
# ) -> List[RiderProfile]:
#     """
#     Find eligible rider candidates based on location and availability.
    
#     Strategy:
#     1. Find available riders nearby
#     2. For SPLIT/URGENT: exclude riders with active orders
#     3. Expand radius progressively if needed
#     """
#     candidates = []
#     radius = URGENT_RADIUS_KM if is_urgent else INITIAL_RADIUS_KM
#     max_radius = URGENT_RADIUS_KM if is_urgent else MAX_RADIUS_KM
#     existing_ids = set()
    
#     if exclude_rider_id:
#         existing_ids.add(exclude_rider_id)
    
#     while len(candidates) < top_n and radius <= max_radius:
#         try:
#             # Query all available riders
#             riders = await RiderProfile.filter(
#                 is_available=True
#             ).prefetch_related("current_location").all()
            
#             # Calculate distances and filter by radius
#             rider_distances = []
#             for r in riders:
#                 if r.id in existing_ids:
#                     continue
                
#                 loc = r.current_location
#                 if not loc:
#                     continue
                
#                 dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
#                 if dist <= radius:
#                     rider_distances.append((r, dist))
#                     existing_ids.add(r.id)
            
#             # Sort by distance and append
#             rider_distances.sort(key=lambda x: x[1])
#             candidates.extend(rider_distances)
            
#         except Exception as e:
#             logger.error(f"Database query error at radius {radius}km: {str(e)}")
        
#         if len(candidates) >= top_n:
#             break
        
#         radius += RADIUS_STEP_KM
    
#     # Remove duplicates and return top N
#     seen_ids = set()
#     result = []
#     for rider, _ in candidates:
#         if rider.id not in seen_ids:
#             result.append(rider)
#             seen_ids.add(rider.id)
#             if len(result) >= top_n:
#                 break
    
#     logger.info(f"Found {len(result)} candidate riders (urgent={is_urgent})")
#     return result

# async def send_offer_to_rider(
#     order_id: str,
#     rider_id: int,
#     is_urgent: bool = False
# ) -> bool:
#     """Send order offer to a single rider."""
#     try:
#         order = await Order.get_or_none(id=order_id)
#         rider = await RiderProfile.get_or_none(id=rider_id)
        
#         if not order or not rider:
#             logger.error(f"Order {order_id} or Rider {rider_id} not found")
#             return False
        
#         # Create OrderOffer record
#         offer = await OrderOffer.create(
#             order=order,
#             rider=rider,
#             status="PENDING",
#             is_urgent=is_urgent,
#             created_at=datetime.utcnow()
#         )
        
#         # Send WebSocket notification
#         ws_success = await notify_rider_websocket(rider_id, order, "order_offer")
        
#         # Send push notification
#         is_urgent_order = order.delivery_type == DeliveryTypeEnum.URGENT
#         notification_title = "🚨 URGENT: Medicine Delivery" if is_urgent_order else "New Order Offer"
#         notification_body = f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
#         push_success = await notify_rider_pushnotification(rider_id, notification_title, notification_body)
        
#         # Update WorkDay stats
#         today = date.today()
#         workday, _ = await WorkDay.get_or_create(
#             rider=rider,
#             date=today,
#             defaults={"hours_worked": 0.0, "order_offer_count": 0}
#         )
#         workday.order_offer_count += 1
#         await workday.save()
        
#         logger.info(f"Offer sent to rider {rider_id} for order {order_id}")
#         return ws_success or push_success
#     except Exception as e:
#         logger.error(f"Error sending offer to rider {rider_id}: {str(e)}")
#         return False

# async def offer_order_sequentially(
#     order_id: str,
#     candidate_riders: List[RiderProfile],
#     background_tasks: BackgroundTasks
# ):
#     """Offer order to riders sequentially with timeout logic."""
#     try:
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             logger.error(f"Order {order_id} not found for sequential offering")
#             return
        
#         is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
        
#         for idx, rider in enumerate(candidate_riders):
#             # Check if order is still available
#             await order.refresh_from_db()
#             if order.status != OrderStatus.CONFIRMED:
#                 logger.info(f"Order {order_id} already accepted, stopping offers")
#                 break
            
#             try:
#                 # Send offer
#                 success = await send_offer_to_rider(order.id, rider.id, is_urgent)
#                 if not success:
#                     logger.warning(f"Failed to send offer to rider {rider.id}")
#                     continue
                
#                 logger.info(f"Order {order_id} offered to rider {rider.id} ({idx + 1}/{len(candidate_riders)})")
                
#                 if is_urgent:
#                     # Wait 60 seconds for urgent order
#                     await asyncio.sleep(URGENT_OFFER_TIMEOUT)
                    
#                     # Check if rider accepted or rejected
#                     await order.refresh_from_db()
#                     offer = await OrderOffer.filter(
#                         order=order,
#                         rider=rider
#                     ).first()
                    
#                     if offer and offer.status == "PENDING":
#                         # Auto-timeout
#                         offer.status = "TIMEOUT"
#                         offer.responded_at = datetime.utcnow()
#                         await offer.save()
#                         logger.info(f"Offer to rider {rider.id} timed out (60s)")
#                     elif offer and offer.status == "REJECTED":
#                         logger.info(f"Rider {rider.id} rejected order {order_id}")
#                     elif offer and offer.status == "ACCEPTED":
#                         break
#             except asyncio.CancelledError:
#                 logger.warning(f"Sequential offering task cancelled for order {order_id}")
#                 break
#             except Exception as e:
#                 logger.error(f"Error offering order {order_id} to rider {rider.id}: {str(e)}")
#                 continue
#     except Exception as e:
#         logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")

# async def offer_order_broadcast(
#     order_id: str,
#     candidate_riders: List[RiderProfile],
#     background_tasks: BackgroundTasks
# ):
#     """Offer order to all riders simultaneously."""
#     try:
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             logger.error(f"Order {order_id} not found for broadcast offering")
#             return
        
#         # Send offers concurrently
#         tasks = [
#             send_offer_to_rider(order.id, rider.id, is_urgent=False)
#             for rider in candidate_riders
#         ]
#         results = await asyncio.gather(*tasks, return_exceptions=True)
        
#         successful = sum(1 for r in results if r is True)
#         logger.info(f"Broadcast offers sent to {len(candidate_riders)} riders for order {order_id} ({successful} successful)")
#     except Exception as e:
#         logger.error(f"Error in broadcast offering for order {order_id}: {str(e)}")

# # ============================================================================
# # VENDOR ENDPOINTS: Create Offers (Vendor Confirms Order)
# # ============================================================================

# @router.post("/vendor/create-offers/{parent_order_id}/")
# async def vendor_create_offers(
#     request: Request,
#     parent_order_id: str,
#     prepare_time: int = Form(...),
#     background_tasks: BackgroundTasks = BackgroundTasks(),
#     top_n: int = 20,
#     current_user: User = Depends(get_current_user),
#     redis=Depends(get_redis)
# ):
#     """
#     VENDOR CONFIRMS ORDERS and creates offers for riders.
    
#     Called by vendor after receiving orders.
    
#     Flow:
#     1. Get all child orders under parent_order_id
#     2. Determine delivery streams (urgent medicine, combined, split)
#     3. For each stream, find riders and send offers
#     4. Update order status to CONFIRMED
    
#     Restrictions:
#     - Only vendors can call this
#     - All child orders must be from same parent
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     if not current_user.is_vendor:
#         raise HTTPException(status_code=403, detail=translate("Only vendors can create offers", lang))
    
#     if top_n <= 0 or top_n > 100:
#         raise HTTPException(status_code=400, detail=translate("Invalid top_n parameter (1-100)", lang))
    
#     try:
#         # Get parent order to determine type (combined/split)
#         parent_orders = await Order.filter(parent_order_id=parent_order_id).all()
#         if not parent_orders:
#             raise HTTPException(status_code=404, detail="Parent order not found")
        
#         # Get vendor profile
#         vendor_profile = await VendorProfile.get_or_none(user=current_user)
#         if not vendor_profile:
#             raise HTTPException(status_code=404, detail="Vendor profile not found")
        
#         # Get all child orders under this parent
#         child_orders = await Order.filter(parent_order_id=parent_order_id).prefetch_related(
#             "items__item", "user"
#         ).all()
        
#         if not child_orders:
#             raise HTTPException(status_code=404, detail="No child orders found")
        
#         # All orders should have same delivery type
#         first_order = child_orders[0]
#         delivery_type = first_order.delivery_type
        
#         logger.info(f"Vendor processing {len(child_orders)} child orders (type={delivery_type})")
        
#         processed_orders = []
        
#         # Process each child order
#         for order in child_orders:
#             order_items = await OrderItem.filter(order=order).all()
#             if not order_items:
#                 continue
            
#             # Categorize items
#             item_ids = [oi.item_id for oi in order_items]
#             items = await Item.filter(id__in=item_ids).all()
#             categories = {itm.id: itm.category for itm in items}
            
#             has_medicine = any(categories.get(iid) == "MEDICINE" for iid in item_ids)
#             has_non_medicine = any(categories.get(iid) and categories.get(iid) != "MEDICINE" for iid in item_ids)
#             urgent_medicine = order.delivery_type == DeliveryTypeEnum.URGENT and has_medicine
            
#             logger.info(f"Order {order.id}: medicine={has_medicine}, non_medicine={has_non_medicine}, urgent_medicine={urgent_medicine}")
            
#             # Determine delivery streams
#             order_data = {
#                 "delivery_option": {
#                     "type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type
#                 }
#             }
            
#             streams = determine_delivery_streams(
#                 order_data,
#                 has_medicine=has_medicine,
#                 has_non_medicine=has_non_medicine,
#                 urgent_medicine=urgent_medicine
#             )
            
#             logger.info(f"Order {order.id} has {len(streams)} stream(s)")
            
#             # For each stream, find riders
#             for stream in streams:
#                 stream_type = stream["type"]
#                 is_urgent = stream["is_urgent"]
#                 delivery_type_str = stream["delivery_type"]
                
#                 # Find candidate riders
#                 candidates = await find_candidate_riders(
#                     vendor_profile.latitude,
#                     vendor_profile.longitude,
#                     is_urgent=is_urgent,
#                     top_n=top_n,
#                     redis=redis
#                 )
                
#                 if not candidates:
#                     logger.warning(f"No riders available for order {order.id} stream {stream_type}")
#                     continue
                
#                 # Update order status and metadata
#                 order.status = OrderStatus.CONFIRMED
#                 order.metadata = order.metadata or {}
#                 order.metadata["streams"] = order.metadata.get("streams", [])
#                 order.metadata["streams"].append({
#                     "stream_type": stream_type,
#                     "is_urgent": is_urgent,
#                     "candidate_riders": [r.id for r in candidates],
#                     "offered_at": datetime.utcnow().isoformat()
#                 })
#                 order.prepare_time = prepare_time
#                 await order.save()
                
#                 # Send offers based on stream type
#                 if is_urgent:
#                     # Sequential for urgent
#                     background_tasks.add_task(
#                         offer_order_sequentially,
#                         order.id,
#                         candidates,
#                         background_tasks
#                     )
#                 else:
#                     # Broadcast for combined/split
#                     background_tasks.add_task(
#                         offer_order_broadcast,
#                         order.id,
#                         candidates,
#                         background_tasks
#                     )
                
#                 processed_orders.append({
#                     "order_id": order.id,
#                     "stream_type": stream_type,
#                     "is_urgent": is_urgent,
#                     "candidate_count": len(candidates)
#                 })
        
#         return translate({
#             "success": True,
#             "message": f"Offers created for {len(processed_orders)} order stream(s)",
#             "data": {
#                 "parent_order_id": parent_order_id,
#                 "processed_orders": processed_orders
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error creating vendor offers: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# # ============================================================================
# # RIDER ENDPOINTS: View Offers & Accept Orders
# # ============================================================================

# @router.get("/rider/offers/")
# async def get_rider_order_offers(
#     request: Request,
#     current_user: User = Depends(get_current_user),
#     limit: int = Query(10, ge=1, le=100),
#     offset: int = Query(0, ge=0)
# ):
#     """
#     Get all pending order offers for current rider.
    
#     Returns list of offers with order details.
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         rider_profile = await RiderProfile.get_or_none(user=current_user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider profile")
        
#         # Get pending offers
#         offers = await OrderOffer.filter(
#             rider=rider_profile,
#             status="PENDING"
#         ).prefetch_related("order__user", "order__items__item").order_by("-created_at").offset(offset).limit(limit).all()
        
#         total = await OrderOffer.filter(rider=rider_profile, status="PENDING").count()
        
#         result = []
#         for offer in offers:
#             order = offer.order
#             items = []
#             for oi in order.items:
#                 items.append({
#                     "item_id": oi.item_id,
#                     "title": oi.title,
#                     "price": oi.price,
#                     "quantity": oi.quantity
#                 })
            
#             # Check if rider has active orders (for URGENT/SPLIT restrictions)
#             can_accept = True
#             restriction_reason = None
            
#             if order.delivery_type in [DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT]:
#                 active_orders = await Order.filter(
#                     rider=rider_profile,
#                     status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.PREPARED, OrderStatus.OUT_FOR_DELIVERY]
#                 ).count()
                
#                 if active_orders > 0:
#                     can_accept = False
#                     restriction_reason = f"You have {active_orders} active URGENT/SPLIT order(s). Complete them first."
            
#             # Calculate time remaining for offer
#             offer_expires_at = offer.created_at + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
#             time_remaining = (offer_expires_at - datetime.utcnow()).total_seconds()
            
#             result.append({
#                 "offer_id": offer.id,
#                 "order_id": order.id,
#                 "parent_order_id": order.parent_order_id,
#                 "customer_name": order.user.name,
#                 "delivery_type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type,
#                 "items": items,
#                 "total": float(order.total),
#                 "base_rate": float(order.base_rate),
#                 "distance_bonus": float(order.distance_bonus),
#                 "is_urgent": offer.is_urgent,
#                 "prepare_time_minutes": order.prepare_time,
#                 "time_remaining_seconds": max(0, int(time_remaining)),
#                 "can_accept": can_accept,
#                 "restriction_reason": restriction_reason,
#                 "offered_at": offer.created_at.isoformat()
#             })
        
#         return translate({
#             "success": True,
#             "total": total,
#             "limit": limit,
#             "offset": offset,
#             "offers": result
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error fetching rider offers: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# @router.post("/rider/accept/{order_id}/")
# async def accept_order(
#     request: Request,
#     order_id: str,
#     current_user: User = Depends(get_current_user),
#     redis=Depends(get_redis),
#     background_tasks: BackgroundTasks = BackgroundTasks()
# ):
#     """
#     RIDER accepts an order.
    
#     Flow:
#     1. Claim order via Redis (prevent race condition)
#     2. Validate order status
#     3. Assign rider to order
#     4. Mark offer as ACCEPTED
#     5. Reject all other offers
#     6. Check restrictions (URGENT/SPLIT)
#     7. Send notifications
    
#     Returns: Order details with assignment info
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Get rider profile
#         rider_profile = await RiderProfile.get_or_none(user=current_user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider profile")
        
#         # Use Redis to prevent race condition
#         claim_key = f"order_claim:{order_id}"
#         claimed = await redis.set(claim_key, str(current_user.id), nx=True, ex=30)
#         if not claimed:
#             raise HTTPException(status_code=400, detail="Order already claimed by another rider")
        
#         # Get order
#         order = await Order.get_or_none(id=order_id).prefetch_related("user", "vendor", "items__item")
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Validate order status
#         if order.status != OrderStatus.CONFIRMED:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot accept order with status: {order.status.value if hasattr(order.status, 'value') else order.status}"
#             )
        
#         # Check delivery restrictions for URGENT/SPLIT
#         if order.delivery_type in [DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT]:
#             active_orders = await Order.filter(
#                 rider=rider_profile,
#                 status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.PREPARED, OrderStatus.OUT_FOR_DELIVERY]
#             ).count()
            
#             if active_orders > 0:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Rider has active URGENT/SPLIT order. Cannot accept another."
#                 )
        
#         # Assign rider
#         order.rider = rider_profile
#         order.status = OrderStatus.PROCESSING
#         order.accepted_at = datetime.utcnow()
        
#         # Calculate payout
#         vendor = await VendorProfile.get_or_none(id=order.vendor_id)
#         if vendor and rider_profile.current_location:
#             distance = haversine(
#                 vendor.latitude,
#                 vendor.longitude,
#                 rider_profile.current_location.latitude,
#                 rider_profile.current_location.longitude
#             )
#             order.pickup_distance_km = distance
            
#             # Calculate delivery fee based on type
#             delivery_type = order.delivery_type.value if hasattr(order.delivery_type, 'value') else str(order.delivery_type)
#             fee = calculate_delivery_fee(delivery_type, distance)
#             order.base_rate = Decimal(str(fee))
        
#         await order.save()
        
#         # Mark offer as ACCEPTED
#         offer = await OrderOffer.get_or_none(order=order, rider=rider_profile)
#         if offer:
#             offer.status = "ACCEPTED"
#             offer.accepted_at = datetime.utcnow()
#             await offer.save()
        
#         # Reject all other offers
#         other_offers = await OrderOffer.filter(order=order).exclude(rider=rider_profile).all()
#         for other_offer in other_offers:
#             if other_offer.status == "PENDING":
#                 other_offer.status = "REJECTED"
#                 other_offer.rejected_at = datetime.utcnow()
#                 await other_offer.save()
        
#         # Send notifications
#         try:
#             await send_notification(
#                 order.user.id,
#                 "Rider Assigned",
#                 f"Rider assigned to your order #{order_id}"
#             )
            
#             vendor_user = await User.get_or_none(id=order.vendor_id)
#             if vendor_user:
#                 await send_notification(
#                     vendor_user.id,
#                     "Order Accepted",
#                     f"Rider accepted order #{order_id}"
#                 )
#         except Exception as e:
#             logger.warning(f"Notification error: {str(e)}")
        
#         # Start chat channel between rider and customer
#         try:
#             await start_chat(current_user.id, order.user.id, order.id)
#         except Exception as e:
#             logger.warning(f"Chat channel error: {str(e)}")
        
#         return translate({
#             "success": True,
#             "message": "Order accepted successfully",
#             "data": {
#                 "order_id": order.id,
#                 "status": order.status.value if hasattr(order.status, 'value') else order.status,
#                 "pickup_distance_km": order.pickup_distance_km,
#                 "base_rate": float(order.base_rate),
#                 "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error accepting order: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# @router.post("/rider/reject/{order_id}/")
# async def reject_order(
#     request: Request,
#     order_id: str,
#     reject_data: OrderRejectRequest,
#     current_user: User = Depends(get_current_user)
# ):
#     """RIDER rejects an order offer."""
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         rider_profile = await RiderProfile.get_or_none(user=current_user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Not a rider profile")
        
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Find and update offer
#         offer = await OrderOffer.get_or_none(order=order, rider=rider_profile)
#         if not offer:
#             raise HTTPException(status_code=404, detail="Offer not found")
        
#         if offer.status != "PENDING":
#             raise HTTPException(status_code=400, detail="Can only reject pending offers")
        
#         offer.status = "REJECTED"
#         offer.reject_reason = reject_data.reason
#         offer.responded_at = datetime.utcnow()
#         await offer.save()
        
#         # Update WorkDay stats
#         today = date.today()
#         workday, _ = await WorkDay.get_or_create(
#             rider=rider_profile,
#             date=today,
#             defaults={"hours_worked": 0.0, "rejection_count": 0}
#         )
#         workday.rejection_count += 1
#         await workday.save()
        
#         logger.info(f"Rider {rider_profile.id} rejected order {order_id}: {reject_data.reason}")
        
#         return translate({
#             "success": True,
#             "message": "Order rejected",
#             "order_id": order_id
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error rejecting order: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")











# ============================================================================
# VENDOR CONFIRM ORDER ENDPOINT
# ============================================================================

# @router.post("/vendors/orders/{order_id}/confirm")
# async def vendor_confirm_order(
#     request: Request,
#     order_id: str,
#     current_user: User = Depends(get_current_user),
#     redis = Depends(get_redis),
#     background_tasks: BackgroundTasks = BackgroundTasks()
# ):
#     """
#     Vendor confirms their portion of an order.
    
#     Logic:
#     - URGENT orders: Auto-assign rider immediately after confirmation
#     - SPLIT orders: Trigger rider broadcast offers after confirmation
#     - COMBINED orders: Check if ALL vendors confirmed, then trigger broadcast
#     - Mixed urgent+non-urgent: Urgent gets auto-assigned, non-urgent waits
    
#     Returns: Order details with confirmation status and next steps
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Verify vendor
#         if not current_user.is_vendor:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Only vendors can confirm orders"
#             )
        
#         # Get order
#         order = await Order.get_or_none(id=order_id).prefetch_related(
#             'user', 'items__item', 'vendor'
#         )
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Verify vendor ownership
#         if order.vendor_id != current_user.id:
#             raise HTTPException(
#                 status_code=403,
#                 detail="You are not authorized to confirm this order"
#             )
        
#         # Check order status - can only confirm pending or processing
#         current_status = (
#             order.status.value 
#             if hasattr(order.status, 'value') 
#             else str(order.status)
#         ).lower()
        
#         if current_status not in ["pending", "processing"]:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot confirm order with status: {current_status}"
#             )
        
#         # Get order type and metadata
#         order_type = "combined"
#         requires_all_confirmations = False
#         if order.metadata and "order_type" in order.metadata:
#             order_type = order.metadata["order_type"]
#         if order.metadata and "requires_all_vendor_confirmations" in order.metadata:
#             requires_all_confirmations = order.metadata["requires_all_vendor_confirmations"]
        
#         # Update metadata - track vendor confirmations
#         order.metadata = order.metadata or {}
#         order.metadata["vendor_confirmations"] = order.metadata.get("vendor_confirmations", {})
#         order.metadata["vendor_confirmations"][str(current_user.id)] = {
#             "confirmed_at": datetime.utcnow().isoformat(),
#             "confirmed": True
#         }
        
#         # Get parent order for combined orders
#         parent_order_id = order.parent_order_id
#         related_orders = await Order.filter(
#             parent_order_id=parent_order_id
#         ).all() if parent_order_id else [order]
        
#         # Check if all vendors confirmed (for combined/split orders)
#         all_confirmed = await _check_all_vendors_confirmed(
#             related_orders, order.metadata
#         )
        
#         # Update order status
#         if order_type == "urgent":
#             # URGENT: Auto-assign rider immediately
#             order.status = OrderStatus.CONFIRMED
#             await order.save()
            
#             # Get vendor location
#             vendor_profile = await VendorProfile.get_or_none(user=current_user)
#             if vendor_profile:
#                 # Find and auto-assign nearest rider
#                 background_tasks.add_task(
#                     _auto_assign_rider_for_urgent,
#                     order.id,
#                     vendor_profile.latitude,
#                     vendor_profile.longitude,
#                     redis
#                 )
            
#             response_msg = f"Order confirmed. Assigning nearest rider for urgent delivery..."
            
#         elif order_type == "split":
#             # SPLIT: Broadcast to riders immediately after this vendor confirms
#             order.status = OrderStatus.CONFIRMED
#             await order.save()
            
#             vendor_profile = await VendorProfile.get_or_none(user=current_user)
#             if vendor_profile:
#                 # Broadcast rider offers for this split order
#                 background_tasks.add_task(
#                     _broadcast_rider_offers,
#                     order.id,
#                     vendor_profile.latitude,
#                     vendor_profile.longitude,
#                     is_urgent=False,
#                     redis=redis
#                 )
            
#             response_msg = f"Order confirmed. Finding available riders..."
            
#         elif order_type == "combined" and all_confirmed:
#             # COMBINED: All vendors confirmed, now broadcast
#             order.status = OrderStatus.CONFIRMED
#             await order.save()
            
#             # Update all related orders with confirmation status
#             for related_order in related_orders:
#                 related_order.metadata = related_order.metadata or {}
#                 related_order.metadata["all_vendors_confirmed"] = True
#                 related_order.status = OrderStatus.CONFIRMED
#                 await related_order.save()
            
#             vendor_profile = await VendorProfile.get_or_none(user=current_user)
#             if vendor_profile:
#                 # Broadcast to riders
#                 background_tasks.add_task(
#                     _broadcast_rider_offers,
#                     order.id,
#                     vendor_profile.latitude,
#                     vendor_profile.longitude,
#                     is_urgent=False,
#                     redis=redis
#                 )
            
#             response_msg = f"All vendors confirmed. Finding available riders..."
            
#         elif order_type == "combined" and not all_confirmed:
#             # COMBINED: Still waiting for other vendors
#             order.status = OrderStatus.PROCESSING
#             await order.save()
            
#             pending_count = len(related_orders) - len(
#                 order.metadata.get("vendor_confirmations", {})
#             )
#             response_msg = f"Order confirmed. Waiting for {pending_count} more vendor(s)..."
        
#         else:
#             # Default update
#             order.status = OrderStatus.CONFIRMED
#             await order.save()
#             response_msg = "Order confirmed successfully"
        
#         # Send notifications
#         try:
#             # Notify customer
#             await send_notification(
#                 order.user_id,
#                 "Vendor Confirmed",
#                 f"Vendor confirmed order #{order.id}"
#             )
            
#             # Broadcast via WebSocket
#             await manager.send_to(
#                 {
#                     "type": "vendor_confirmed",
#                     "order_id": order.id,
#                     "parent_order_id": parent_order_id,
#                     "order_type": order_type,
#                     "timestamp": datetime.utcnow().isoformat()
#                 },
#                 "customers",
#                 str(order.user_id),
#                 "orders"
#             )
#         except Exception as e:
#             print(f"[CONFIRM] Notification error: {e}")
        
#         # Build response
#         vendor_profile = await VendorProfile.get_or_none(user=current_user)
#         return {
#             "success": True,
#             "message": response_msg,
#             "data": {
#                 "order_id": order.id,
#                 "parent_order_id": parent_order_id,
#                 "order_type": order_type,
#                 "status": "confirmed",
#                 "vendor_id": current_user.id,
#                 "vendor_name": current_user.name,
#                 "all_vendors_confirmed": all_confirmed,
#                 "pending_vendors": (
#                     len(related_orders) - len(order.metadata.get("vendor_confirmations", {}))
#                     if order_type == "combined" else 0
#                 ),
#                 "next_action": (
#                     "Waiting for available rider" if all_confirmed 
#                     else "Waiting for other vendors"
#                 ),
#                 "preparation_required": order_type == "split"  # Each split order needs prep
#             }
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"[CONFIRM] Error: {e}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # ============================================================================
# # RIDER ACCEPT ORDER ENDPOINT
# # ============================================================================

# @router.post("/riders/orders/{order_id}/accept")
# async def rider_accept_order(
#     request: Request,
#     order_id: str,
#     current_user: User = Depends(get_current_user),
#     redis = Depends(get_redis),
#     background_tasks: BackgroundTasks = BackgroundTasks()
# ):
#     """
#     Rider accepts an order offer.
    
#     Logic:
#     - URGENT orders: Already auto-assigned, just confirm acceptance
#     - SPLIT/COMBINED orders: Lock rider, expire other offers
#     - Block rider from accepting other orders until delivery
    
#     Returns: Assignment confirmation with pickup/delivery details
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Verify rider
#         rider_profile = await RiderProfile.get_or_none(user=current_user)
#         if not rider_profile:
#             raise HTTPException(status_code=403, detail="Rider profile not found")
        
#         # Check rider availability
#         if not rider_profile.is_available:
#             raise HTTPException(
#                 status_code=400,
#                 detail="You are currently not available for orders"
#             )
        
#         # Get order
#         order = await Order.get_or_none(id=order_id).prefetch_related(
#             'user', 'items__item', 'vendor', 'rider'
#         )
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Get order type
#         order_type = "combined"
#         if order.metadata and "order_type" in order.metadata:
#             order_type = order.metadata["order_type"]
        
#         # Check rider lock for SPLIT/COMBINED orders
#         if order_type in ["split", "combined"]:
#             # Check if rider already has active orders
#             active_orders = await Order.filter(
#                 rider=rider_profile,
#                 status__in=[
#                     OrderStatus.CONFIRMED,
#                     OrderStatus.SHIPPED,
#                     OrderStatus.PREPARED,
#                     OrderStatus.OUT_FOR_DELIVERY
#                 ]
#             ).count()
            
#             if active_orders > 0:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"You have {active_orders} active order(s). Complete them first before accepting new orders."
#                 )
        
#         # For URGENT orders: verify rider is auto-assigned
#         if order_type == "urgent":
#             if order.rider_id and order.rider_id != rider_profile.id:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="This urgent order is assigned to another rider"
#                 )
#             # Mark as accepted (if not already)
        
#         # Update order with rider assignment
#         order.rider_id = rider_profile.id
#         order.status = OrderStatus.OUT_FOR_DELIVERY
        
#         # For SPLIT/COMBINED: Lock rider
#         if order_type in ["split", "combined"]:
#             order.metadata = order.metadata or {}
#             order.metadata["rider_locked"] = True
#             order.metadata["rider_locked_at"] = datetime.utcnow().isoformat()
        
#         await order.save()
        
#         # Create/update OrderOffer record
#         order_offer = await OrderOffer.filter(
#             order=order,
#             rider=rider_profile
#         ).first()
        
#         if order_offer:
#             order_offer.status = "ACCEPTED"
#             order_offer.responded_at = datetime.utcnow()
#             await order_offer.save()
#         else:
#             # Create offer record if doesn't exist (for auto-assigned)
#             await OrderOffer.create(
#                 order=order,
#                 rider=rider_profile,
#                 status="ACCEPTED",
#                 is_urgent=(order_type == "urgent"),
#                 created_at=datetime.utcnow(),
#                 responded_at=datetime.utcnow()
#             )
        
#         # For SPLIT/COMBINED: Expire other offers
#         if order_type in ["split", "combined"]:
#             background_tasks.add_task(
#                 _expire_other_offers,
#                 order.id,
#                 rider_profile.id
#             )
        
#         # Send notifications
#         try:
#             # Notify vendor
#             if order.vendor:
#                 await send_notification(
#                     order.vendor_id,
#                     "Rider Assigned",
#                     f"Rider {current_user.name} assigned to order #{order.id}"
#                 )
            
#             # Notify customer
#             await send_notification(
#                 order.user_id,
#                 "Rider Assigned",
#                 f"Rider {current_user.name} is picking up your order"
#             )
            
#             # Broadcast via WebSocket
#             await manager.send_to(
#                 {
#                     "type": "rider_assigned",
#                     "order_id": order.id,
#                     "rider_id": rider_profile.id,
#                     "rider_name": current_user.name,
#                     "rider_phone": current_user.phone,
#                     "timestamp": datetime.utcnow().isoformat()
#                 },
#                 "vendors",
#                 str(order.vendor_id),
#                 "orders"
#             )
            
#             await manager.send_to(
#                 {
#                     "type": "rider_assigned",
#                     "order_id": order.id,
#                     "rider_id": rider_profile.id,
#                     "rider_name": current_user.name
#                 },
#                 "customers",
#                 str(order.user_id),
#                 "orders"
#             )
#         except Exception as e:
#             print(f"[ACCEPT] Notification error: {e}")
        
#         # Build response
#         vendor_info = order.metadata.get("vendor_info", {}) if order.metadata else {}
#         return {
#             "success": True,
#             "message": f"Order accepted successfully. Heading to pickup location.",
#             "data": {
#                 "order_id": order.id,
#                 "parent_order_id": order.parent_order_id,
#                 "order_type": order_type,
#                 "rider_id": rider_profile.id,
#                 "rider_name": current_user.name,
#                 "rider_phone": current_user.phone,
#                 "status": "out_for_delivery",
#                 "vendor_location": {
#                     "latitude": vendor_info.get("store_latitude"),
#                     "longitude": vendor_info.get("store_longitude"),
#                     "name": vendor_info.get("store_name", "Store")
#                 },
#                 "estimated_pickup_time": "5-10 minutes",
#                 "customer_info": {
#                     "name": order.user.name if order.user else "Customer",
#                     "phone": order.user.phone if order.user else None
#                 }
#             }
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"[ACCEPT] Error: {e}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # ============================================================================
# # ORDER STATUS ENDPOINT
# # ============================================================================

# @router.get("/orders/{order_id}/status")
# async def get_order_status(
#     request: Request,
#     order_id: str,
#     current_user: User = Depends(get_current_user)
# ):
#     """
#     Get real-time order status with type-specific information.
    
#     Returns:
#     - Order type (combined, split, urgent)
#     - Vendor confirmation status (for combined orders)
#     - Rider assignment status
#     - Next actions required
#     - Estimated times
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         # Get order
#         order = await Order.get_or_none(id=order_id).prefetch_related(
#             'user', 'vendor', 'rider'
#         )
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Verify authorization (customer, vendor, or rider)
#         is_customer = order.user_id == current_user.id
#         is_vendor = order.vendor_id == current_user.id
#         is_rider = order.rider and order.rider.user_id == current_user.id
        
#         if not (is_customer or is_vendor or is_rider):
#             raise HTTPException(
#                 status_code=403,
#                 detail="Not authorized to view this order"
#             )
        
#         # Extract order type and metadata
#         order_type = "combined"
#         if order.metadata and "order_type" in order.metadata:
#             order_type = order.metadata["order_type"]
        
#         vendor_confirmations = (
#             order.metadata.get("vendor_confirmations", {})
#             if order.metadata else {}
#         )
        
#         current_status = (
#             order.status.value 
#             if hasattr(order.status, 'value') 
#             else str(order.status)
#         ).lower()
        
#         # Build status response
#         status_response = {
#             "order_id": order.id,
#             "parent_order_id": order.parent_order_id,
#             "order_type": order_type,
#             "current_status": current_status,
#             "total_amount": float(order.total),
#             "created_at": order.order_date.isoformat() if order.order_date else None
#         }
        
#         # Add type-specific information
#         if order_type == "combined":
#             # Get all related orders for confirmation tracking
#             related_orders = await Order.filter(
#                 parent_order_id=order.parent_order_id
#             ).all() if order.parent_order_id else [order]
            
#             vendor_count = len(related_orders)
#             confirmed_count = len(vendor_confirmations)
            
#             status_response.update({
#                 "vendor_confirmations": {
#                     "total": vendor_count,
#                     "confirmed": confirmed_count,
#                     "pending": vendor_count - confirmed_count,
#                     "details": vendor_confirmations
#                 },
#                 "all_confirmed": confirmed_count == vendor_count,
#                 "awaiting_vendors": current_status == "processing" and confirmed_count < vendor_count
#             })
        
#         elif order_type == "split":
#             status_response.update({
#                 "independent_vendor": True,
#                 "vendor_confirmed": len(vendor_confirmations) > 0,
#                 "ready_for_rider": current_status in ["confirmed", "out_for_delivery"]
#             })
        
#         elif order_type == "urgent":
#             status_response.update({
#                 "is_urgent": True,
#                 "vendor_confirmed": len(vendor_confirmations) > 0,
#                 "rider_auto_assigned": order.rider_id is not None,
#                 "rider_locked": order.metadata.get("rider_locked", False) if order.metadata else False
#             })
        
#         # Add rider assignment info if applicable
#         if order.rider:
#             status_response.update({
#                 "rider_assigned": {
#                     "rider_id": order.rider.id,
#                     "rider_name": order.rider.user.name if order.rider.user else None,
#                     "rider_phone": order.rider.user.phone if order.rider.user else None,
#                     "assigned_at": order.metadata.get("rider_locked_at") if order.metadata else None
#                 },
#                 "rider_locked": True
#             })
#         else:
#             status_response.update({
#                 "rider_assigned": None,
#                 "rider_locked": False
#             })
        
#         # Add next action
#         if current_status == "pending" or current_status == "processing":
#             if order_type == "combined":
#                 next_action = "Waiting for vendor confirmations" if len(vendor_confirmations) < vendor_count else "Waiting for rider"
#             elif order_type == "split":
#                 next_action = "Waiting for vendor confirmation" if not vendor_confirmations else "Waiting for rider"
#             elif order_type == "urgent":
#                 next_action = "Waiting for vendor confirmation" if not vendor_confirmations else "Rider auto-assigned"
#             else:
#                 next_action = "Processing order"
#         else:
#             next_action = None
        
#         status_response["next_action"] = next_action
        
#         return {
#             "success": True,
#             "data": status_response
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"[STATUS] Error: {e}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# # ============================================================================
# # HELPER FUNCTIONS
# # ============================================================================

# async def _check_all_vendors_confirmed(related_orders: list, metadata: dict) -> bool:
#     """Check if all vendors for this order have confirmed"""
#     vendor_confirmations = metadata.get("vendor_confirmations", {})
#     vendor_ids = {order.vendor_id for order in related_orders}
#     confirmed_vendors = set(int(v) for v in vendor_confirmations.keys())
#     return vendor_ids == confirmed_vendors


# async def _auto_assign_rider_for_urgent(
#     order_id: str,
#     vendor_lat: float,
#     vendor_lng: float,
#     redis
# ):
#     """
#     Auto-assign nearest available rider for urgent orders.
#     Called in background task after vendor confirms.
#     """
#     try:
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             print(f"[AUTO_ASSIGN] Order {order_id} not found")
#             return
        
#         # Find nearest available riders (within 10km for urgent)
#         riders = await _find_nearby_riders(
#             vendor_lat, vendor_lng,
#             radius_km=10.0,
#             is_urgent=True,
#             redis=redis
#         )
        
#         if not riders:
#             print(f"[AUTO_ASSIGN] No riders available for order {order_id}")
#             # TODO: Send notification to vendor/customer - no riders available
#             return
        
#         # Assign first nearest rider
#         assigned_rider = riders[0]
#         order.rider_id = assigned_rider.id
#         order.status = OrderStatus.CONFIRMED
        
#         # Create OrderOffer
#         await OrderOffer.create(
#             order=order,
#             rider=assigned_rider,
#             status="AUTO_ASSIGNED",
#             is_urgent=True,
#             created_at=datetime.utcnow()
#         )
        
#         await order.save()
        
#         # Send notification to rider
#         try:
#             await send_notification(
#                 assigned_rider.user_id,
#                 "🚨 URGENT ORDER ASSIGNED",
#                 f"Urgent order #{order.id} assigned. Pick up immediately!"
#             )
#         except:
#             pass
        
#         print(f"[AUTO_ASSIGN] Assigned rider {assigned_rider.id} to urgent order {order_id}")
    
#     except Exception as e:
#         print(f"[AUTO_ASSIGN] Error: {e}")


# async def _broadcast_rider_offers(
#     order_id: str,
#     vendor_lat: float,
#     vendor_lng: float,
#     is_urgent: bool = False,
#     redis = None
# ):
#     """
#     Broadcast order offer to all available riders.
#     First rider to accept wins.
#     """
#     try:
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             print(f"[BROADCAST] Order {order_id} not found")
#             return
        
#         # Find available riders
#         riders = await _find_nearby_riders(
#             vendor_lat, vendor_lng,
#             radius_km=3.0 if not is_urgent else 10.0,
#             is_urgent=is_urgent,
#             redis=redis
#         )
        
#         if not riders:
#             print(f"[BROADCAST] No riders available for order {order_id}")
#             # TODO: Handle no riders scenario
#             return
        
#         # Create offers for all riders
#         for rider in riders:
#             try:
#                 offer = await OrderOffer.create(
#                     order=order,
#                     rider=rider,
#                     status="PENDING",
#                     is_urgent=is_urgent,
#                     created_at=datetime.utcnow()
#                 )
                
#                 # Send notification
#                 try:
#                     await send_notification(
#                         rider.user_id,
#                         "New Order Offer",
#                         f"Order #{order_id} - ₹{order.total}"
#                     )
#                 except:
#                     pass
#             except:
#                 continue
        
#         print(f"[BROADCAST] Order {order_id} offered to {len(riders)} riders")
    
#     except Exception as e:
#         print(f"[BROADCAST] Error: {e}")


# async def _expire_other_offers(order_id: str, accepted_rider_id: int):
#     """
#     Expire other rider offers for this order after acceptance.
#     """
#     try:
#         # Get all pending offers for this order
#         pending_offers = await OrderOffer.filter(
#             order_id=order_id,
#             status="PENDING"
#         ).exclude(rider_id=accepted_rider_id).all()
        
#         for offer in pending_offers:
#             offer.status = "EXPIRED"
#             offer.responded_at = datetime.utcnow()
#             await offer.save()
        
#         print(f"[EXPIRE] Expired {len(pending_offers)} offers for order {order_id}")
#     except Exception as e:
#         print(f"[EXPIRE] Error: {e}")


# async def _find_nearby_riders(
#     latitude: float,
#     longitude: float,
#     radius_km: float = 3.0,
#     is_urgent: bool = False,
#     redis = None
# ) -> list:
#     """
#     Find available riders within radius.
#     Uses Redis geo-spatial queries if available, falls back to database.
#     """
#     try:
#         riders = []
        
#         # Try Redis first (if available)
#         if redis:
#             try:
#                 # Execute GEORADIUS command
#                 geo_results = await redis.execute_command(
#                     "GEORADIUS",
#                     "riders_locations",
#                     longitude,
#                     latitude,
#                     radius_km,
#                     "km",
#                     "ASC",
#                     "COUNT",
#                     20
#                 )
                
#                 if geo_results:
#                     rider_ids = [int(x) for x in geo_results]
#                     riders = await RiderProfile.filter(
#                         id__in=rider_ids,
#                         is_available=True
#                     ).all()
#                     return riders
#             except:
#                 pass
        
#         # Fallback: Query all available riders and filter by distance
#         all_riders = await RiderProfile.filter(
#             is_available=True
#         ).prefetch_related("current_location").all()
        
#         from app.utils.geo import haversine
        
#         for rider in all_riders:
#             if rider.current_location:
#                 distance = haversine(
#                     latitude, longitude,
#                     rider.current_location.latitude,
#                     rider.current_location.longitude
#                 )
#                 if distance <= radius_km:
#                     riders.append(rider)
        
#         # Sort by distance
#         riders.sort(
#             key=lambda r: haversine(
#                 latitude, longitude,
#                 r.current_location.latitude,
#                 r.current_location.longitude
#             ) if r.current_location else float('inf')
#         )
        
#         return riders[:20]  # Return top 20 nearest riders
    
#     except Exception as e:
#         print(f"[FIND_RIDERS] Error: {e}")
#         return []









OFFER_TIMEOUT_SECONDS = 60  # adjust as needed


# ============================================================================
# VENDOR CONFIRM ORDER
# ============================================================================

@router.post("/vendors/orders/{order_id}/confirm")
async def vendor_confirm_order(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Vendor confirms their portion of an order.

    Logic:
    - URGENT orders: Auto-assign rider immediately after confirmation
    - SPLIT orders: Trigger rider broadcast offers after confirmation
    - COMBINED orders: Check if ALL vendors confirmed (by group key), then trigger broadcast

    Returns: Order details with confirmation status and next steps
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()

    try:
        # Verify vendor
        if not current_user.is_vendor:
            raise HTTPException(
                status_code=403,
                detail="Only vendors can confirm orders",
            )

        # Get order
        order = await Order.get_or_none(id=order_id).prefetch_related(
            "user", "items__item", "vendor"
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Verify vendor ownership
        if order.vendor_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to confirm this order",
            )

        # Check order status
        current_status = (
            order.status.value if hasattr(order.status, "value") else str(order.status)
        ).lower()
        if current_status not in ["pending", "processing"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot confirm order with status: {current_status}",
            )

        # Get order type
        # order_type = "combined"
        # if order.metadata and "order_type" in order.metadata:
        #     order_type = order.metadata["order_type"]
        order_type = order.delivery_type


        # Determine group key and group orders
        group_key = order.parent_order_id or order.id

        # All orders that belong to this combined group (including this order)
        related_orders = await Order.filter(
            # if parent_order_id is set, group by that, otherwise single order group
            parent_order_id=group_key
        ).all()

        # For non-combined orders, there may be no parent_order_id; ensure at least current order
        if not related_orders:
            related_orders = [order]

        # Group master: use the first order in group to hold shared metadata
        group_master = related_orders[0]

        # Initialize group metadata
        group_master.metadata = group_master.metadata or {}
        group_master.metadata["vendor_confirmations"] = group_master.metadata.get(
            "vendor_confirmations", {}
        )

        # Store confirmation on group master keyed by vendor id
        group_master.metadata["vendor_confirmations"][str(current_user.id)] = {
            "confirmed_at": datetime.utcnow().isoformat(),
            "confirmed": True,
        }
        await group_master.save()

        shared_metadata = group_master.metadata or {}
        vendor_confirmations = shared_metadata.get("vendor_confirmations", {})

        # Check if all vendors confirmed: compare vendor ids across group with confirmed ids
        all_confirmed = await _check_all_vendors_confirmed(related_orders, shared_metadata)

        # Status & rider flow
        if order_type == "urgent":
            order.status = OrderStatus.CONFIRMED
            await order.save()

            vendor_profile = await VendorProfile.get_or_none(user=current_user)
            if vendor_profile:
                background_tasks.add_task(
                    _auto_assign_rider_for_urgent,
                    order.id,
                    vendor_profile.latitude,
                    vendor_profile.longitude,
                    redis,
                )
            response_msg = "Order confirmed. Assigning nearest rider for urgent delivery..."

        elif order_type == "split":
            order.status = OrderStatus.CONFIRMED
            await order.save()

            vendor_profile = await VendorProfile.get_or_none(user=current_user)
            if vendor_profile:
                background_tasks.add_task(
                    _broadcast_rider_offers,
                    order.id,
                    vendor_profile.latitude,
                    vendor_profile.longitude,
                    is_urgent=False,
                    redis=redis,
                )
            response_msg = "Order confirmed. Finding available riders..."

        elif order_type == "combined" and all_confirmed:
            # Mark all group orders as confirmed
            for related in related_orders:
                related.metadata = related.metadata or {}
                related.metadata["all_vendors_confirmed"] = True
                related.status = OrderStatus.CONFIRMED
                await related.save()

            vendor_profile = await VendorProfile.get_or_none(user=current_user)
            if vendor_profile:
                # Use group_key as the broadcast id (any id is fine as long as rider accepts one)
                broadcast_order_id = group_key if group_key != order.id else order.id
                background_tasks.add_task(
                    _broadcast_rider_offers,
                    broadcast_order_id,
                    vendor_profile.latitude,
                    vendor_profile.longitude,
                    is_urgent=False,
                    redis=redis,
                )

            response_msg = "All vendors confirmed. Finding available riders..."

        elif order_type == "combined" and not all_confirmed:
            order.status = OrderStatus.PROCESSING
            await order.save()

            pending_count = len(related_orders) - len(vendor_confirmations)
            response_msg = f"Order confirmed. Waiting for {pending_count} more vendor(s)..."

        else:
            order.status = OrderStatus.CONFIRMED
            await order.save()
            response_msg = "Order confirmed successfully"

        # Notifications
        try:
            await send_notification(
                order.user_id,
                "Vendor Confirmed",
                f"Vendor confirmed order #{order.id}",
            )

            await manager.send_to(
                {
                    "type": "vendor_confirmed",
                    "order_id": order.id,
                    "parent_order_id": order.parent_order_id,
                    "order_type": order_type,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "customers",
                str(order.user_id),
                "orders",
            )
        except Exception as e:
            print(f"[CONFIRM] Notification error: {e}")

        pending_vendors = (
            len(related_orders) - len(vendor_confirmations)
            if order_type == "combined"
            else 0
        )

        return {
            "success": True,
            "message": response_msg,
            "data": {
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "order_type": order_type,
                "status": "confirmed",
                "vendor_id": current_user.id,
                "vendor_name": current_user.name,
                "all_vendors_confirmed": all_confirmed,
                "pending_vendors": pending_vendors,
                "next_action": (
                    "Waiting for available rider"
                    if all_confirmed
                    else "Waiting for other vendors"
                )
                if order_type == "combined"
                else None,
                "preparation_required": order_type == "split",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CONFIRM] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# ============================================================================
# RIDER ACCEPT ORDER
# ============================================================================

@router.post("/riders/orders/{order_id}/accept")
async def rider_accept_order(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Rider accepts an order offer.

    Logic:
    - URGENT orders: Already auto-assigned, just confirm acceptance
    - SPLIT/COMBINED orders: Lock rider, expire other offers
    - For COMBINED: one acceptance assigns rider to all orders with same parent_order_id

    Returns: Assignment confirmation with pickup/delivery details
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()

    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user).prefetch_related(
            "current_location"
        )
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Rider profile not found")

        if not rider_profile.is_available:
            raise HTTPException(
                status_code=400,
                detail="You are currently not available for orders",
            )

        # Base order of the offer
        order = await Order.get_or_none(id=order_id).prefetch_related(
            "user", "items__item", "vendor", "rider"
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order_type = "combined"
        if order.metadata and "order_type" in order.metadata:
            order_type = order.metadata["order_type"]

        # Rider active lock for split/combined
        if order_type in ["split", "combined", "urgent"]:
            active_orders = await Order.filter(
                rider=rider_profile,
                status__in=[
                    OrderStatus.CONFIRMED,
                    OrderStatus.SHIPPED,
                    OrderStatus.PREPARED,
                    OrderStatus.OUT_FOR_DELIVERY,
                ],
            ).count()
            if active_orders > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"You have {active_orders} active order(s). Complete them first before accepting new orders.",
                )

        # URGENT assignment check
        if order_type == "urgent":
            if order.rider_id and order.rider_id != rider_profile.id:
                raise HTTPException(
                    status_code=400,
                    detail="This urgent order is assigned to another rider",
                )

        # Determine combined group: by parent_order_id or single
        if order_type == "combined":
            group_key = order.parent_order_id or order.id
            group_orders = await Order.filter(parent_order_id=group_key).prefetch_related(
                "vendor"
            )
            if not group_orders:
                group_orders = [order]
        else:
            group_orders = [order]

        # Fees / distance setup
        fees_config = await RiderFeesAndBonuses.first()
        base_rate_single = float(fees_config.rider_delivery_fee or 44.00)
        distance_bonus_per_km = float(fees_config.distance_bonus_per_km or 1.0)

        #customer = order.user
        customer = await CustomerProfile.get_or_none(user_id=order.user_id)
        if not customer:
            raise HTTPException(
                status_code=400,
                detail="Customer profile not found",
            )

        customer_lat = customer.customer_lat #getattr(customer, "customer_lat", None)
        customer_lng = customer.customer_lng #getattr(customer, "customer_lng", None)

        current_location = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)

        if not current_location:
            raise HTTPException(
                status_code=400,
                detail="Rider location not available",
            )

        rider_lat = current_location.latitude
        rider_lng = current_location.longitude

        # Calculate pickup distances
        total_pickup_dist = 0.0
        pickup_distances = []  # (order, pickup_dist)
        total_prepare_time = 0

        for o in group_orders:
            vendor_info = o.metadata.get("vendor_info", {}) if o.metadata else {}
            v_lat = vendor_info.get("store_latitude")
            v_lng = vendor_info.get("store_longitude")

            if v_lat is None or v_lng is None:
                if o.vendor_id:
                    v_profile = await VendorProfile.get_or_none(user_id=o.vendor_id)
                    if v_profile:
                        v_lat = v_profile.latitude
                        v_lng = v_profile.longitude

            if v_lat is None or v_lng is None:
                continue

            pickup_dist = haversine(
                rider_lat,
                rider_lng,
                v_lat,
                v_lng,
            )
            print(f"rider lat lng: {rider_lat},{rider_lng} to vendor lat lng: {v_lat},{v_lng} = {pickup_dist} km")
            pickup_distances.append((o, pickup_dist))
            total_pickup_dist += pickup_dist
            rider_lat = v_lat
            rider_lng = v_lng
            total_prepare_time += o.prepare_time or 10

        # Delivery distance from last pickup to customer
        delivery_dist = 0.0
        if customer_lat is not None and customer_lng is not None and pickup_distances:
            last_order, _ = pickup_distances[-1]
            vendor_info = last_order.metadata.get("vendor_info", {}) if last_order.metadata else {}
            v_lat = vendor_info.get("store_latitude")
            v_lng = vendor_info.get("store_longitude")
            if v_lat is not None and v_lng is not None:                   
                delivery_dist = haversine(v_lat, v_lng, customer_lat, customer_lng)
                print(f"last vendor lat lng: {v_lat},{v_lng} to customer lat lng: {customer_lat},{customer_lng} = {delivery_dist} km")

        total_dist = total_pickup_dist + delivery_dist

        print(f"total distance: {total_dist} km, pickup: {total_pickup_dist} km, delivery: {delivery_dist} km")

        # Payout
        is_combined = order_type == "combined" and len(group_orders) > 1
        base_rate = base_rate_single
        distance_bonus = max(total_dist - 3, 0) * distance_bonus_per_km

        if is_combined:
            base_rate += (len(group_orders) - 1) * base_rate_single

        pickup_eta_min = int(estimate_eta(total_pickup_dist).total_seconds() / 60)
        delivery_eta_min = int(estimate_eta(delivery_dist).total_seconds() / 60)
        eta_minutes = pickup_eta_min + delivery_eta_min + int(total_prepare_time)

        # Assign rider to all orders in group
        now = datetime.utcnow()

        for o, pickup_dist in pickup_distances:
            o.rider_id = rider_profile.id
            #o.status = OrderStatus.OUT_FOR_DELIVERY

            if order_type in ["split", "combined"]:
                o.metadata = o.metadata or {}
                o.metadata["rider_locked"] = True
                o.metadata["rider_locked_at"] = now.isoformat()

            o.pickup_distance_km = float(round(pickup_dist, 2))
            o.base_rate = Decimal(str(base_rate))
            o.distance_bonus = Decimal(str(round(distance_bonus, 2)))
            o.eta_minutes = eta_minutes
            o.accepted_at = now
            o.expires_at = now + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
            o.metadata = o.metadata or {}
            o.metadata["rider_id"] = rider_profile.id
            o.metadata["accepted_at"] = now.isoformat()

            await o.save()

        if order_type == "urgent" and not pickup_distances:
            order.rider_id = rider_profile.id
            order.status = OrderStatus.OUT_FOR_DELIVERY
            await order.save()

        # Offer record on the base (accepted) order
        offer_order = order
        order_offer = await OrderOffer.filter(
            order=offer_order,
            rider=rider_profile,
        ).first()

        if order_offer:
            order_offer.status = "ACCEPTED"
            order_offer.responded_at = now
            await order_offer.save()
        else:
            await OrderOffer.create(
                order=offer_order,
                rider=rider_profile,
                status="ACCEPTED",
                is_urgent=(order_type == "urgent"),
                created_at=now,
                responded_at=now,
            )

        # Expire other offers for this group order id
        if order_type in ["split", "combined"]:
            background_tasks.add_task(
                _expire_other_offers,
                offer_order.id,
                rider_profile.id,
            )

        # Notifications
        try:
            # Notify vendors for each order
            for o in group_orders:
                if o.vendor:
                    await send_notification(
                        o.vendor_id,
                        "Rider Assigned",
                        f"Rider {current_user.name} assigned to order #{o.id}",
                    )

                await manager.send_to(
                    {
                        "type": "rider_assigned",
                        "order_id": o.id,
                        "rider_id": rider_profile.id,
                        "rider_name": current_user.name,
                        "rider_phone": current_user.phone,
                        "timestamp": now.isoformat(),
                    },
                    "vendors",
                    str(o.vendor_id),
                    "orders",
                )

            # Notify customer (combined info)
            await send_notification(
                order.user_id,
                "Rider Assigned",
                f"Rider {current_user.name} is picking up your order(s)",
            )

            await manager.send_to(
                {
                    "type": "rider_assigned",
                    "group_key": order.parent_order_id or order.id,
                    "orders": [o.id for o in group_orders],
                    "rider_id": rider_profile.id,
                    "rider_name": current_user.name,
                    "total_payout": float(base_rate + distance_bonus),
                    "eta_minutes": eta_minutes,
                },
                "customers",
                str(order.user_id),
                "orders",
            )

            # Rider combined notification
            if order_type == "combined":
                pickup_list = []
                for o in group_orders:
                    vendor_info = o.metadata.get("vendor_info", {}) if o.metadata else {}
                    pickup_list.append(
                        {
                            "order_id": o.id,
                            "store_name": vendor_info.get("store_name")
                            or (o.vendor.name if o.vendor else "Store"),
                            "amount": float(o.total),
                        }
                    )

                await send_notification(
                    rider_profile.user_id,
                    "Combined Order Accepted",
                    f"You accepted {len(group_orders)} combined orders. Total payout ₹{base_rate + distance_bonus:.2f}.",
                )

                await manager.send_to(
                    {
                        "type": "combined_order_accepted",
                        "group_key": order.parent_order_id or order.id,
                        "orders": pickup_list,
                        "total_orders": len(group_orders),
                        "total_payout": float(base_rate + distance_bonus),
                        "eta_minutes": eta_minutes,
                    },
                    "riders",
                    str(rider_profile.user_id),
                    "orders",
                )

        except Exception as e:
            print(f"[ACCEPT] Notification error: {e}")

        vendor_info = order.metadata.get("vendor_info", {}) if order.metadata else {}
        return {
            "success": True,
            "message": "Order accepted successfully. Heading to pickup location.",
            "data": {
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "order_type": order_type,
                "rider_id": rider_profile.id,
                "rider_name": current_user.name,
                "rider_phone": current_user.phone,
                "status": "out_for_delivery",
                "vendor_location": {
                    "latitude": vendor_info.get("store_latitude"),
                    "longitude": vendor_info.get("store_longitude"),
                    "name": vendor_info.get("store_name", "Store"),
                },
                "estimated_pickup_time": "5-10 minutes",
                "customer_info": {
                    "name": order.user.name if order.user else "Customer",
                    "phone": order.user.phone if order.user else None,
                },
                "combined_orders": [o.id for o in group_orders]
                if order_type == "combined"
                else None,
                "total_payout": float(base_rate + distance_bonus),
                "eta_minutes": eta_minutes,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ACCEPT] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# ============================================================================
# ORDER STATUS
# ============================================================================

@router.get("/orders/{order_id}/status")
async def get_order_status(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get real-time order status with type-specific information.
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()

    try:
        order = await Order.get_or_none(id=order_id).prefetch_related("rider", "user", "vendor")
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        is_customer = order.user_id == current_user.id
        is_vendor = order.vendor_id == current_user.id
        is_rider = order.rider and order.rider.user_id == current_user.id

        if not (is_customer or is_vendor or is_rider):
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view this order",
            )

        order_type = "combined"
        if order.metadata and "order_type" in order.metadata:
            order_type = order.metadata["order_type"]

        # Group key and master for vendor confirmations
        group_key = order.parent_order_id or order.id
        group_orders = await Order.filter(parent_order_id=group_key).all()
        if not group_orders:
            group_orders = [order]
        group_master = group_orders[0]

        vendor_confirmations = (
            group_master.metadata.get("vendor_confirmations", {})
            if group_master.metadata
            else {}
        )

        current_status = (
            order.status.value if hasattr(order.status, "value") else str(order.status)
        ).lower()

        status_response = {
            "order_id": order.id,
            "parent_order_id": order.parent_order_id,
            "order_type": order_type,
            "current_status": current_status,
            "total_amount": float(order.total),
            "created_at": order.order_date.isoformat() if order.order_date else None,
        }

        if order_type == "combined":
            vendor_count = len(group_orders)
            confirmed_count = len(vendor_confirmations)

            status_response.update(
                {
                    "vendor_confirmations": {
                        "total": vendor_count,
                        "confirmed": confirmed_count,
                        "pending": vendor_count - confirmed_count,
                        "details": vendor_confirmations,
                    },
                    "all_confirmed": confirmed_count == vendor_count,
                    "awaiting_vendors": current_status == "processing"
                    and confirmed_count < vendor_count,
                }
            )
        elif order_type == "split":
            status_response.update(
                {
                    "independent_vendor": True,
                    "vendor_confirmed": len(vendor_confirmations) > 0,
                    "ready_for_rider": current_status in ["confirmed", "out_for_delivery"],
                }
            )
        elif order_type == "urgent":
            status_response.update(
                {
                    "is_urgent": True,
                    "vendor_confirmed": len(vendor_confirmations) > 0,
                    "rider_auto_assigned": order.rider_id is not None,
                    "rider_locked": order.metadata.get("rider_locked", False)
                    if order.metadata
                    else False,
                }
            )

        if order.rider:
            status_response.update(
                {
                    "rider_assigned": {
                        "rider_id": order.rider.id,
                        "rider_name": order.rider.user.name if order.rider.user else None,
                        "rider_phone": order.rider.user.phone
                        if order.rider.user
                        else None,
                        "assigned_at": order.metadata.get("rider_locked_at")
                        if order.metadata
                        else None,
                    },
                    "rider_locked": True,
                }
            )
        else:
            status_response.update(
                {
                    "rider_assigned": None,
                    "rider_locked": False,
                }
            )

        if current_status in ["pending", "processing"]:
            if order_type == "combined":
                vendor_count = len(group_orders)
                confirmed_count = len(vendor_confirmations)
                next_action = (
                    "Waiting for vendor confirmations"
                    if confirmed_count < vendor_count
                    else "Waiting for rider"
                )
            elif order_type == "split":
                next_action = (
                    "Waiting for vendor confirmation"
                    if not vendor_confirmations
                    else "Waiting for rider"
                )
            elif order_type == "urgent":
                next_action = (
                    "Waiting for vendor confirmation"
                    if not vendor_confirmations
                    else "Rider auto-assigned"
                )
            else:
                next_action = "Processing order"
        else:
            next_action = None

        status_response["next_action"] = next_action

        return {
            "success": True,
            "data": status_response,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[STATUS] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _check_all_vendors_confirmed(related_orders: list[Order], metadata: dict) -> bool:
    vendor_confirmations = metadata.get("vendor_confirmations", {})
    vendor_ids = {o.vendor_id for o in related_orders}
    confirmed_vendors = set(int(v) for v in vendor_confirmations.keys())
    return vendor_ids == confirmed_vendors


async def _auto_assign_rider_for_urgent(
    order_id: str,
    vendor_lat: float,
    vendor_lng: float,
    redis,
):
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            print(f"[AUTO_ASSIGN] Order {order_id} not found")
            return

        riders = await _find_nearby_riders(
            vendor_lat, vendor_lng, radius_km=10.0, is_urgent=True, redis=redis
        )

        if not riders:
            print(f"[AUTO_ASSIGN] No riders available for order {order_id}")
            return
        
        while riders:
            rider_profile = riders.pop(0)
            active_orders = await Order.filter(
                rider=rider_profile,
                status__in=[
                    OrderStatus.CONFIRMED,
                    OrderStatus.SHIPPED,
                    OrderStatus.PREPARED,
                    OrderStatus.OUT_FOR_DELIVERY,
                ],
            ).count()
            if active_orders > 0:
               continue
            else:
                assigned_rider = rider_profile
                order.rider_id = rider_profile.id
                order.status = OrderStatus.CONFIRMED
                break
        if not assigned_rider:
            print(f"[AUTO_ASSIGN] No available riders found for order {order_id}")
            return
        await OrderOffer.create(
            order=order,
            rider=assigned_rider,
            status="AUTO_ASSIGNED",
            is_urgent=True,
            created_at=datetime.utcnow(),
        )

        await order.save()

        try:
            await manager.send_notification(
                "riders",
                assigned_rider.user_id,
                "🚨 URGENT ORDER ASSIGNED",
                f"Urgent order #{order.id} assigned. Pick up immediately!",
            )
        except Exception:
            pass

        try:
            await send_notification(
                assigned_rider.user_id,
                "🚨 URGENT ORDER ASSIGNED",
                f"Urgent order #{order.id} assigned. Pick up immediately!",
            )
        except Exception:
            pass

        print(f"[AUTO_ASSIGN] Assigned rider {assigned_rider.id} to urgent order {order_id}")

    except Exception as e:
        print(f"[AUTO_ASSIGN] Error: {e}")


async def _broadcast_rider_offers(
    order_id: str,
    vendor_lat: float,
    vendor_lng: float,
    is_urgent: bool = False,
    redis=None,
):
    try:
        orders = None
        order = await Order.get_or_none(id=order_id)
        if not order:
            print(f"[BROADCAST] Order {order_id} not found")
            order = await Order.filter(parent_order_id=order_id).first()
            orders = await Order.filter(parent_order_id=order_id).all()
            if not order:
                print(f"[BROADCAST] No order found for broadcast id {order_id}")
                return
            #return

        riders = await _find_nearby_riders(
            vendor_lat,
            vendor_lng,
            radius_km=3.0 if not is_urgent else 10.0,
            is_urgent=is_urgent,
            redis=redis,
        )

        if not riders:
            print(f"[BROADCAST] No riders available for order {order_id}")
            return
        print(f"orders {orders}")

        for rider in riders:
            try:
                await OrderOffer.create(
                    order=order,
                    rider=rider,
                    status="PENDING",
                    is_urgent=is_urgent,
                    created_at=datetime.utcnow(),
                )
                print(f"[BROADCAST] Offered order {order_id} to rider {rider.id}")
                try:
                    print(f"rider user id {rider.user_id}")
                    await manager.send_notification(
                        "riders",
                        rider.user_id,
                        "New Order Offer",
                        f"you have a new order offer🗣📢. Orders #{', '.join(str(o.id) for o in orders) if orders else order.id}",
                    )
                except Exception:
                    pass

                try:
                    await send_notification(
                        rider.user_id,
                        "New Order Offer",
                        f"Order #{order_id} - ₹{order.total}",
                    )
                except Exception:
                    pass
            except Exception:
                continue

        print(f"[BROADCAST] Order {order_id} offered to {len(riders)} riders")

    except Exception as e:
        print(f"[BROADCAST] Error: {e}")


async def _expire_other_offers(order_id: str, accepted_rider_id: int):
    try:
        pending_offers = (
            await OrderOffer.filter(order_id=order_id, status="PENDING")
            .exclude(rider_id=accepted_rider_id)
            .all()
        )

        for offer in pending_offers:
            offer.status = "EXPIRED"
            offer.responded_at = datetime.utcnow()
            await offer.save()

        print(f"[EXPIRE] Expired {len(pending_offers)} offers for order {order_id}")

    except Exception as e:
        print(f"[EXPIRE] Error: {e}")


async def _find_nearby_riders(
    latitude: float,
    longitude: float,
    radius_km: float = 3.0,
    is_urgent: bool = False,
    redis=None,
) -> list[RiderProfile]:
    try:
        riders = []

        if redis:
            try:
                geo_results = await redis.execute_command(
                    "GEORADIUS",
                    "riders_locations",
                    longitude,
                    latitude,
                    radius_km,
                    "km",
                    "ASC",
                    "COUNT",
                    20,
                )

                if geo_results:
                    rider_ids = [int(x) for x in geo_results]
                    riders = await RiderProfile.filter(
                        id__in=rider_ids,
                        is_available=True,
                    ).all()
                    return riders
            except Exception:
                pass

        all_riders = (
            await RiderProfile.filter(is_available=True)
            .prefetch_related("current_location")
            .all()
        )

        print(f"[FIND_RIDERS] Checking {len(all_riders)} available riders {all_riders}")
        rider_with_distance = []

        for rider in all_riders:
            location = await RiderCurrentLocation.get_or_none(rider_profile=rider)
            if location:
                print(f"[FIND_RIDERS] Rider {rider.id} location: {location.latitude}, {location.longitude}, vendoer: {latitude}, {longitude}")
                distance = haversine(
                    latitude,
                    longitude,
                    location.latitude,
                    location.longitude,
                )
                print(f"[FIND_RIDERS] Rider {rider.id} is {distance:.2f} km away {radius_km} km")
                if distance <= radius_km:
                    rider_with_distance.append((rider, distance))
                    #riders.append(rider)

        rider_with_distance.sort(key=lambda x: x[1])
        riders = [r[0] for r in rider_with_distance]

        return riders[:20]

    except Exception as e:
        print(f"[FIND_RIDERS] Error: {e}")
        return []



# ============================================================================
# RIDER ENDPOINTS: View Active Orders
# ============================================================================

@router.get("/rider/active-orders/")
async def get_rider_active_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all active orders assigned to current rider."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider profile")
        
        # Get active orders
        query = Order.filter(rider=rider_profile).prefetch_related("user", "items__item", "vendor")
        
        if status_filter:
            try:
                status_enum = OrderStatus[status_filter.upper()]
                query = query.filter(status=status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        
        total = await query.count()
        orders = await query.order_by("-accepted_at").offset(offset).limit(limit).all()
        
        result = []
        for order in orders:
            items = []
            for oi in order.items:
                items.append({
                    "item_id": oi.item_id,
                    "title": oi.title,
                    "price": oi.price,
                    "quantity": oi.quantity
                })
            
            result.append({
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "customer_name": order.user.name,
                "customer_phone": order.user.phone,
                "items": items,
                "total": float(order.total),
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "delivery_type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type,
                "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
                "pickup_distance_km": order.pickup_distance_km,
                "base_rate": float(order.base_rate)
            })
        
        return translate({
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "orders": result
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching rider active orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# ============================================================================
# VENDOR ENDPOINTS: View Active Orders
# ============================================================================

@router.get("/vendor/active-orders/")
async def get_vendor_active_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all active orders for current vendor's items."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        vendor_profile = await VendorProfile.get_or_none(user=current_user)
        if not vendor_profile:
            raise HTTPException(status_code=403, detail="Not a vendor profile")
        
        # Get vendor's items
        vendor_items = await Item.filter(vendor=vendor_profile).all()
        vendor_item_ids = [item.id for item in vendor_items]
        
        # Get orders containing vendor's items
        query = Order.filter(items__item_id__in=vendor_item_ids).distinct().prefetch_related(
            "user", "items__item", "rider"
        )
        
        if status_filter:
            try:
                status_enum = OrderStatus[status_filter.upper()]
                query = query.filter(status=status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        
        total = await query.count()
        orders = await query.order_by("-created_at").offset(offset).limit(limit).all()
        
        result = []
        for order in orders:
            # Only include vendor's items
            items = []
            for oi in order.items:
                if oi.item_id in vendor_item_ids:
                    items.append({
                        "item_id": oi.item_id,
                        "title": oi.title,
                        "price": oi.price,
                        "quantity": oi.quantity
                    })
            
            if not items:
                continue
            
            result.append({
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "customer_name": order.user.name,
                "customer_phone": order.user.phone,
                "items": items,
                "total": float(order.total),
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "rider_assigned": order.rider_id is not None,
                "created_at": order.created_at.isoformat()
            })
        
        return translate({
            "success": True,
            "total": len(result),
            "orders": result
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vendor active orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# ============================================================================
# CUSTOMER ENDPOINTS: View Active Orders
# ============================================================================

@router.get("/customer/active-orders/")
async def get_customer_active_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all active orders for current customer."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        # Get customer's orders
        query = Order.filter(user=current_user).prefetch_related("items__item", "rider")
        
        if status_filter:
            try:
                status_enum = OrderStatus[status_filter.upper()]
                query = query.filter(status=status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        
        total = await query.count()
        orders = await query.order_by("-created_at").offset(offset).limit(limit).all()
        
        result = []
        for order in orders:
            items = []
            for oi in order.items:
                items.append({
                    "item_id": oi.item_id,
                    "title": oi.title,
                    "price": oi.price,
                    "quantity": oi.quantity
                })
            
            rider_info = None
            if order.rider:
                rider_info = {
                    "rider_name": order.rider.user.name,
                    "rider_phone": order.rider.user.phone,
                    "rider_location": {
                        "latitude": order.rider.current_location.latitude if order.rider.current_location else None,
                        "longitude": order.rider.current_location.longitude if order.rider.current_location else None
                    }
                }
            
            result.append({
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "items": items,
                "total": float(order.total),
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "delivery_type": order.delivery_type.value if hasattr(order.delivery_type, 'value') else order.delivery_type,
                "rider_info": rider_info,
                "created_at": order.created_at.isoformat()
            })
        
        return translate({
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "orders": result
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching customer active orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# ============================================================================
# CANCELLATION ENDPOINTS
# ============================================================================

@router.post("/cancel/{order_id}/")
async def cancel_order(
    request: Request,
    order_id: str,
    cancel_data: CancelOrderRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Cancel an order (by customer, rider, or vendor).
    
    Rules:
    - Customer can cancel PENDING/PROCESSING/CONFIRMED orders
    - Rider can cancel PROCESSING/CONFIRMED orders
    - Vendor can cancel PROCESSING/CONFIRMED orders
    - Cannot cancel SHIPPED/OUT_FOR_DELIVERY/DELIVERED
    - If paid, mark for refund
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        order = await Order.get_or_none(id=order_id).prefetch_related("user", "rider", "items__item")
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Authorization check
        is_customer = order.user_id == current_user.id
        is_rider = order.rider and order.rider.user_id == current_user.id
        is_vendor = current_user.is_vendor
        
        if not (is_customer or is_rider or is_vendor):
            raise HTTPException(status_code=403, detail="Not authorized to cancel this order")
        
        # Check cancellable status
        current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        cancellable_statuses = ["pending", "processing", "confirmed"]
        
        if current_status.lower() not in cancellable_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel order with status: {current_status}"
            )
        
        # If paid, mark for refund
        if order.payment_status == "paid":
            if order.metadata is None:
                order.metadata = {}
            order.metadata["refund_requested"] = True
            order.metadata["refund_requested_at"] = datetime.utcnow().isoformat()
            order.metadata["refund_reason"] = cancel_data.reason or "User cancelled"
        
        # Update order
        old_status = current_status
        order.status = OrderStatus.CANCELLED
        order.reason = cancel_data.reason or "Cancelled"
        order.updated_at = datetime.utcnow()
        await order.save()
        
        # Send notifications
        try:
            # Notify customer
            await send_notification(
                order.user_id,
                "Order Cancelled",
                f"Your order #{order_id} has been cancelled. Reason: {order.reason}"
            )
            
            # Notify rider
            if order.rider:
                await send_notification(
                    order.rider.user_id,
                    "Order Cancelled",
                    f"Order #{order_id} has been cancelled."
                )
            
            # Notify vendors
            vendor_ids = set()
            for oi in order.items:
                vendor_ids.add(oi.item.vendor_id)
            
            for vendor_id in vendor_ids:
                vendor = await VendorProfile.get_or_none(id=vendor_id)
                if vendor:
                    await send_notification(
                        vendor.user_id,
                        "Order Cancelled",
                        f"Order #{order_id} has been cancelled."
                    )
        except Exception as e:
            logger.warning(f"Notification error: {str(e)}")
        
        return translate({
            "success": True,
            "message": "Order cancelled successfully",
            "data": {
                "order_id": order_id,
                "old_status": old_status,
                "new_status": "cancelled",
                "refund_requested": order.payment_status == "paid"
            }
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# ============================================================================
# ORDER STATUS UPDATE ENDPOINTS
# ============================================================================

@router.post("/vendor/mark-shipped/{order_id}/")
async def vendor_mark_shipped(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """VENDOR marks order as shipped (handed to rider)."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        if not current_user.is_vendor:
            raise HTTPException(status_code=403, detail="Only vendors can update order status")
        
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != OrderStatus.PROCESSING:
            raise HTTPException(
                status_code=400,
                detail=f"Can only mark PROCESSING orders as shipped"
            )
        
        order.status = OrderStatus.SHIPPED
        await order.save()
        
        # Notify rider and customer
        if order.rider:
            await send_notification(
                order.rider.user_id,
                "Order Ready",
                f"Order #{order_id} is ready for pickup"
            )
        
        await send_notification(
            order.user_id,
            "Order Shipped",
            f"Your order #{order_id} has been handed to the rider"
        )
        
        return translate({
            "success": True,
            "message": "Order marked as shipped",
            "order_id": order_id
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking order as shipped: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/rider/mark-on-way/{order_id}/")
async def rider_mark_on_way(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """RIDER marks order as on the way."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider")
        
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.rider_id != rider_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        if order.status != OrderStatus.SHIPPED:
            raise HTTPException(
                status_code=400,
                detail=f"Can only mark SHIPPED orders as on the way"
            )
        
        order.status = OrderStatus.OUT_FOR_DELIVERY
        await order.save()
        
        # Notify customer
        await send_notification(
            order.user_id,
            "Order On The Way",
            f"Your order #{order_id} is on the way"
        )
        
        return translate({
            "success": True,
            "message": "Order marked as on the way",
            "order_id": order_id
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking order as on the way: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/rider/mark-delivered/{order_id}/")
async def rider_mark_delivered(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """RIDER marks order as delivered."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider")
        
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.rider_id != rider_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        if order.status != OrderStatus.OUT_FOR_DELIVERY:
            raise HTTPException(
                status_code=400,
                detail=f"Can only mark OUT_FOR_DELIVERY orders as delivered"
            )
        
        order.status = OrderStatus.DELIVERED
        order.completed_at = datetime.utcnow()
        await order.save()
        
        # Notify customer
        await send_notification(
            order.user_id,
            "Order Delivered",
            f"Your order #{order_id} has been delivered successfully"
        )
        
        return translate({
            "success": True,
            "message": "Order marked as delivered",
            "order_id": order_id,
            "delivered_at": order.completed_at.isoformat() if order.completed_at else None
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking order as delivered: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    


@router.get("/rider-offered-orders/")
async def get_rider_offered_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all orders offered to the current rider."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider profile")
        
        # Get offered orders
        query = OrderOffer.filter(rider=rider_profile, status="PENDING").prefetch_related("order__user", "order__items__item", "order__vendor")
        
        total = await query.count()
        offers = await query.order_by("-created_at").offset(offset).limit(limit).all()
        
        result = []
        for offer in offers:
            order = offer.order
            items = []
            orders = await Order.filter(parent_order_id=order.parent_order_id).all().prefetch_related("items__item", "user")
            for order in orders:
                for oi in order.items:
                    items.append({
                        "item_id": oi.item_id,
                        "title": oi.title,
                        "price": oi.price,
                        "quantity": oi.quantity
                    })
            
            result.append({
                "offer_id": offer.id,
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "customer_name": order.user.name,
                "customer_phone": order.user.phone,
                "items": items,
                "total": float(order.total),
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "offered_at": offer.created_at.isoformat() if offer.created_at else None
            })
        
        return translate({
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "offers": result
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching rider offered orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    


@router.get("/orders/")
async def list_orders(
    request: Request,
    skip: int = Query(default=0),
    limit: int = Query(default=10),
    user: User = Depends(get_current_user),
):
    """
    List orders assigned to the current rider.
    Supports pagination with skip and limit.
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    try:
        rider = await RiderProfile.get_or_none(user=user)
        if not rider:
            raise HTTPException(status_code=403, detail="Not a rider")

        orders = await Order.filter(
            rider=rider
        ).offset(skip).limit(limit).order_by("-created_at").group_by("parent_order_id").all()



        return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    
