from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Query, Request
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import json
import asyncio

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
router = APIRouter(tags=['Rider Orders'])

# Constants
OFFER_TIMEOUT_SECONDS = 1200  # 20 minutes total offer validity
URGENT_OFFER_TIMEOUT = 60     # 1 minute per rider for urgent orders
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

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert datetime to UTC if not already"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def notify_rider_websocket(
    rider_id: int,
    order: Order,
    notification_type: str = "order_offer"
) -> bool:
    """
    Send WebSocket notification to rider.
    Returns: True if successful, False otherwise
    """
    try:
        payload = {
            "type": notification_type,
            "order_id": str(order.id),
            "timestamp": datetime.utcnow().isoformat(),
            "delivery_type": str(order.delivery_type)
        }

        rider = await RiderProfile.get_or_none(id=rider_id)
        if not rider:
            logger.error(f"Rider {rider_id} not found for WebSocket notification")
            return False

        # Send via WebSocket manager
        await manager.send_notification(
            "riders",
            str(rider.user_id),
            "New Order Offer",
            f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
        )
        logger.info(f"WebSocket notification sent to rider {rider_id} for order {order.id}")
        return True

    except Exception as e:
        logger.error(f"WebSocket notification error for rider {rider_id}: {str(e)}")
        return False


async def notify_rider_pushnotification(
    rider_id: int,
    title: str,
    body: str
) -> bool:
    """
    Send push notification to rider.
    Returns: True if successful, False otherwise
    """
    try:
        rider = await RiderProfile.get_or_none(id=rider_id)
        if not rider or not rider.user_id:
            logger.warning(f"Rider {rider_id} not found or no user_id for push notification")
            return False

        await send_notification(rider.user_id, title, body)
        logger.info(f"Push notification sent to rider {rider_id}: {title}")
        return True

    except Exception as e:
        logger.error(f"Push notification error for rider {rider_id}: {str(e)}")
        return False


async def find_candidate_riders(
    vendor_lat: float,
    vendor_lng: float,
    is_urgent: bool = False,
    top_n: int = 20,
    redis=None
) -> List[RiderProfile]:
    """
    Find eligible rider candidates based on location and availability.
    
    Strategy:
    1. Try Redis GEO search (GEORADIUS for Redis < 6.2 compatibility)
    2. Fall back to database query
    3. Expand radius progressively if needed
    """
    candidates = []
    radius = URGENT_RADIUS_KM if is_urgent else INITIAL_RADIUS_KM
    max_radius = URGENT_RADIUS_KM if is_urgent else MAX_RADIUS_KM
    existing_ids = set()

    while len(candidates) < top_n and radius <= max_radius:
        candidate_rider_ids = []

        # Try Redis GEO search (GEORADIUS for compatibility)
        if redis:
            try:
                # Use GEORADIUS instead of GEOSEARCH for Redis < 6.2 compatibility
                geo_res = await redis.execute_command(
                    "GEORADIUS",
                    GEO_REDIS_KEY,
                    vendor_lng,
                    vendor_lat,
                    radius,
                    "km",
                    "ASC",
                    "COUNT",
                    int(top_n * 3)
                )

                if geo_res:
                    candidate_rider_ids = [
                        int(x) for x in geo_res
                        if int(x) not in existing_ids
                    ]

            except Exception as e:
                logger.warning(f"Redis GEORADIUS search failed: {str(e)}")
                candidate_rider_ids = []

        # Get riders from database
        try:
            if candidate_rider_ids:
                riders = await RiderProfile.filter(
                    id__in=candidate_rider_ids,
                    is_available=True
                ).prefetch_related("current_location").all()
            else:
                # Fallback: query all available riders
                riders = await RiderProfile.filter(
                    is_available=True
                ).prefetch_related("current_location").all()

            # Calculate distances and filter by radius
            rider_distances = []
            for r in riders:
                if r.id in existing_ids:
                    continue

                loc = r.current_location
                if not loc:
                    continue

                dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
                if dist <= radius:
                    rider_distances.append((r, dist))
                    existing_ids.add(r.id)

            # Sort by distance and append
            rider_distances.sort(key=lambda x: x[1])
            candidates.extend(rider_distances)

        except Exception as e:
            logger.error(f"Database query error at radius {radius}km: {str(e)}")

        radius += RADIUS_STEP_KM

    # Remove duplicates and return top N
    seen_ids = set()
    result = []
    for rider, _ in candidates:
        if rider.id not in seen_ids:
            result.append(rider)
            seen_ids.add(rider.id)
            if len(result) >= top_n:
                break

    logger.info(f"Found {len(result)} candidate riders (urgent={is_urgent})")
    return result


async def send_offer_to_rider(
    order_id: str,
    rider_id: int,
    is_urgent: bool = False
) -> bool:
    """
    Send order offer to a single rider (used for broadcast offers).
    Creates OrderOffer record and sends notifications.
    Returns: True if successful
    """
    try:
        order = await Order.get_or_none(id=order_id)
        rider = await RiderProfile.get_or_none(id=rider_id)

        if not order or not rider:
            logger.error(f"Order {order_id} or Rider {rider_id} not found")
            return False

        # Create OrderOffer record
        offer = await OrderOffer.create(
            order=order,
            rider=rider,
            status="PENDING",
            is_urgent=is_urgent,
            created_at=datetime.utcnow()
        )

        # Send WebSocket notification
        ws_success = await notify_rider_websocket(rider_id, order, "order_offer")

        # Send push notification
        is_urgent_order = order.delivery_type == DeliveryTypeEnum.URGENT
        notification_title = "🚨 URGENT: Medicine Delivery" if is_urgent_order else "New Order Offer"
        notification_body = f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus if order.base_rate else '0'}"
        push_success = await notify_rider_pushnotification(rider_id, notification_title, notification_body)

        # Update WorkDay stats
        today = date.today()
        workday, _ = await WorkDay.get_or_create(
            rider=rider,
            date=today,
            defaults={"hours_worked": 0.0, "order_offer_count": 0}
        )
        workday.order_offer_count += 1
        await workday.save()

        logger.info(f"Offer sent to rider {rider_id} for order {order_id}")
        return ws_success or push_success

    except Exception as e:
        logger.error(f"Error sending offer to rider {rider_id}: {str(e)}")
        return False


async def offer_order_sequentially(
    order_id: str,
    candidate_riders: List[RiderProfile],
    background_tasks: BackgroundTasks
):
    """
    Offer order to riders sequentially with timeout logic.
    
    For URGENT orders:
    - Offer to one rider, wait 60 seconds for response
    - If no response, mark as TIMEOUT and move to next rider
    - Move to next immediately if rejected
    
    For NORMAL orders:
    - Offer and continue immediately (no wait)
    """
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            logger.error(f"Order {order_id} not found for sequential offering")
            return

        is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT

        for idx, rider in enumerate(candidate_riders):
            # Check if order is still available (not yet accepted)
            await order.refresh_from_db()
            if order.status != OrderStatus.PROCESSING:
                logger.info(f"Order {order_id} already accepted, stopping offers")
                break

            try:
                # Send offer to this rider
                success = await send_offer_to_rider(order.id, rider.id, is_urgent)
                if not success:
                    logger.warning(f"Failed to send offer to rider {rider.id}")

                logger.info(f"Order {order_id} offered to rider {rider.id} ({idx + 1}/{len(candidate_riders)})")

                if is_urgent:
                    # Wait 60 seconds for urgent order
                    await asyncio.sleep(URGENT_OFFER_TIMEOUT)

                    # Check if rider accepted or rejected
                    await order.refresh_from_db()
                    offer = await OrderOffer.filter(
                        order=order,
                        rider=rider
                    ).first()

                    if offer and offer.status == "PENDING":
                        # Auto-timeout: mark as timeout
                        offer.status = "TIMEOUT"
                        offer.responded_at = datetime.utcnow()
                        await offer.save()
                        logger.info(f"Offer to rider {rider.id} timed out (60s)")
                        # Continue to next rider
                    elif offer and offer.status == "REJECTED":
                        logger.info(f"Rider {rider.id} rejected order {order_id}")
                        # Continue to next rider
                    elif offer and offer.status == "ACCEPTED":
                        # Rider accepted - order will be marked as accepted elsewhere
                        break
                else:
                    # For non-urgent, just continue immediately
                    pass

            except asyncio.CancelledError:
                logger.warning(f"Sequential offering task cancelled for order {order_id}")
                break
            except Exception as e:
                logger.error(f"Error offering order {order_id} to rider {rider.id}: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")


async def offer_order_broadcast(
    order_id: str,
    candidate_riders: List[RiderProfile],
    background_tasks: BackgroundTasks
):
    """
    Offer order to all riders simultaneously (for SPLIT and COMBINED orders).
    
    First rider to accept wins.
    Others count offer but don't get accepted.
    """
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            logger.error(f"Order {order_id} not found for broadcast offering")
            return

        # Send offers to all riders concurrently
        tasks = [
            send_offer_to_rider(order.id, rider.id, is_urgent=False)
            for rider in candidate_riders
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)

        logger.info(f"Broadcast offers sent to {len(candidate_riders)} riders for order {order_id} ({successful} successful)")

        # Wait for acceptance (rider will accept in accept_order endpoint)
        # This task just sends the offers

    except Exception as e:
        logger.error(f"Error in broadcast offering for order {order_id}: {str(e)}")


# ============================================================================
# ORDER ENDPOINTS
# ============================================================================

@router.post("/orders/create-offer/{order_id}/")
async def create_order_offer(
    request: Request,
    order_id: str,
    background_tasks: BackgroundTasks,
    prepare_time: int = Form(...),
    top_n: int = 20,
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    Create order offer and find eligible riders.
    Called by VENDOR after order is placed.
    
    Flow:
    1. Find candidate riders based on location
    2. Validate order details
    3. For SPLIT/COMBINED: broadcast to all riders
    4. For URGENT: sequential with 1-minute timeouts per rider
    5. For NORMAL: sequential without timeouts
    
    Returns: Offer creation status with candidate count
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail=translate("Only vendors can create offers", lang))

    if top_n <= 0 or top_n > 100:
        raise HTTPException(status_code=400, detail=translate("Invalid top_n parameter (1-100)", lang))

    try:
        # Validate order exists and get related entities
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail=translate("Order not found", lang))

        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(status_code=404, detail=translate("Order item not found", lang))

        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        customer = await CustomerProfile.get_or_none(id=order.user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Validate order is in correct status
        if order.status not in [OrderStatus.PENDING, OrderStatus.PROCESSING]:
            raise HTTPException(status_code=400, detail="Order already being processed or delivered")

        # Determine delivery type
        is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
        is_split = order.delivery_type == DeliveryTypeEnum.SPLIT
        is_combined = order.is_combined or (order.delivery_type == DeliveryTypeEnum.COMBINED)

        # Find candidate riders
        candidates = await find_candidate_riders(
            vendor.latitude,
            vendor.longitude,
            is_urgent=is_urgent,
            top_n=top_n,
            redis=redis
        )

        if not candidates:
            raise HTTPException(status_code=400, detail="No riders available in area")

        # Update order status to PROCESSING (waiting for acceptance)
        order.status = OrderStatus.CONFIRMED
        order.metadata = order.metadata or {}
        order.metadata["candidate_riders"] = [r.id for r in candidates]
        order.metadata["offered_at"] = datetime.utcnow().isoformat()
        order.metadata["delivery_type"] = str(order.delivery_type)
        order.prepare_time = prepare_time
        await order.save()

        # Deduct stock
        item.stock -= order_item.quantity
        await item.save()

        # Queue offering based on order type
        if is_split or is_combined:
            # Broadcast to all riders simultaneously
            background_tasks.add_task(
                offer_order_broadcast,
                order_id,
                candidates,
                background_tasks
            )
        else:
            # Sequential offering (for URGENT and NORMAL)
            background_tasks.add_task(
                offer_order_sequentially,
                order_id,
                candidates,
                background_tasks
            )

        return translate({
            "status": "offer_created",
            "order_id": order_id,
            "candidate_count": len(candidates),
            "delivery_type": str(order.delivery_type),
            "is_urgent": is_urgent,
            "is_split": is_split,
            "is_combined": is_combined,
            "message": f"Order offers sent to {len(candidates)} nearby riders"
        }, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order offer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/accept/{order_id}/")
async def accept_order(
    request: Request,
    order_id: str,
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    RIDER accepts an order.
    
    Flow:
    1. Claim order via Redis (race condition prevention)
    2. Validate order status and delivery type restrictions
    3. Verify location data
    4. Calculate payout
    5. Update order with rider assignment
    6. Mark this offer as ACCEPTED
    7. Reject other pending offers for this order
    8. Send notifications
    9. Start chat channels
    
    Restrictions:
    - URGENT/SPLIT: Cannot accept another order until delivered
    - COMBINED: Can accept other orders
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    try:
        # Get rider profile
        rider_profile = await RiderProfile.get_or_none(user=user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider profile")

        # Use Redis to prevent race condition
        claim_key = f"order_claim:{order_id}"
        claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)

        if not claimed:
            raise HTTPException(status_code=400, detail="Order already claimed by another rider")

        # Get and validate order
        order = await Order.get_or_none(id=order_id)
        if not order:
            await redis.delete(claim_key)
            raise HTTPException(status_code=404, detail="Order not found")

        # Order must be in PROCESSING state
        if order.status != OrderStatus.CONFIRMED:
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available (already accepted or expired)")

        # Check delivery type restrictions
        is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
        is_split = order.delivery_type == DeliveryTypeEnum.SPLIT
        is_combined = order.is_combined or (order.delivery_type == DeliveryTypeEnum.COMBINED)

        # URGENT and SPLIT orders: cannot accept another until delivered
        if is_urgent or is_split:
            active_blocking = await Order.filter(
                rider=rider_profile,
                delivery_type__in=[DeliveryTypeEnum.URGENT, DeliveryTypeEnum.SPLIT],
                status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
            ).first()

            if active_blocking:
                await redis.delete(claim_key)
                raise HTTPException(
                    status_code=400,
                    detail="Cannot accept another urgent/split order until current delivery is complete"
                )

        # COMBINED orders: no restriction (can accept multiple)
        # (other delivery types also have no restriction)

        async with in_transaction():
            # Re-verify order status inside transaction
            order = await Order.get(id=order_id)
            if order.status != OrderStatus.CONFIRMED:
                raise HTTPException(status_code=400, detail="Order not available")

            # Get all required data
            order_item = await OrderItem.get_or_none(order=order)
            if not order_item:
                raise HTTPException(status_code=404, detail="Order item not found")

            item = await Item.get_or_none(id=order_item.item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            vendor = await VendorProfile.get_or_none(id=item.vendor_id)
            if not vendor:
                raise HTTPException(status_code=404, detail="Vendor not found")

            customer = await CustomerProfile.get_or_none(id=order.user_id)
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found")

            loc = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
            if not loc:
                raise HTTPException(status_code=400, detail="Rider location not available")

            # Get fees configuration
            fees_config = await RiderFeesAndBonuses.get_or_none(id=1)
            if not fees_config:
                raise HTTPException(status_code=500, detail="Fees not configured")

            # Calculate distances
            pickup_dist = haversine(
                vendor.latitude, vendor.longitude,
                loc.latitude, loc.longitude
            )

            delivery_dist = haversine(
                vendor.latitude, vendor.longitude,
                customer.customer_lat, customer.customer_lng
            )

            total_dist = pickup_dist + delivery_dist

            # Calculate payout
            base_rate = float(fees_config.rider_delivery_fee or 44.00)

            # Distance bonus: ₹1 per km beyond 3km
            distance_bonus = max(total_dist - 3, 0) * float(fees_config.distance_bonus_per_km or 1.0)

            # For combined orders, add base rate for each additional pickup
            if is_combined and order.combined_pickups:
                base_rate += (len(order.combined_pickups) - 1) * base_rate

            # Estimate ETA
            pickup_eta_min = int(estimate_eta(pickup_dist).total_seconds() / 60)
            delivery_eta_min = int(estimate_eta(delivery_dist).total_seconds() / 60)
            eta_minutes = pickup_eta_min + delivery_eta_min + (order.prepare_time or 10)

            # Update order
            #order.status = OrderStatus.CONFIRMED
            order.rider = rider_profile
            order.pickup_distance_km = Decimal(str(round(pickup_dist, 2)))
            order.base_rate = Decimal(str(base_rate))
            order.distance_bonus = Decimal(str(round(distance_bonus, 2)))
            order.eta_minutes = eta_minutes
            order.accepted_at = datetime.utcnow()
            order.expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
            order.metadata = order.metadata or {}
            order.metadata["rider_id"] = rider_profile.id
            order.metadata["accepted_at"] = datetime.utcnow().isoformat()

            await order.save()

            # Update the OrderOffer record for this rider to ACCEPTED
            offer = await OrderOffer.filter(order=order, rider=rider_profile).first()
            if offer:
                offer.status = "ACCEPTED"
                offer.responded_at = datetime.utcnow()
                await offer.save()

            # Reject all other pending offers for this order
            await OrderOffer.filter(
                order=order
            ).exclude(rider=rider_profile).update(
                status="REJECTED",
                responded_at=datetime.utcnow()
            )

        # Send WebSocket notification to customer and vendor
        notify_payload = {
            "type": "order_accepted",
            "order_id": order_id,
            "rider_id": rider_profile.id,
            "rider_name": user.name,
            "accepted_at": datetime.utcnow().isoformat()
        }

        await redis.publish("order_updates", json.dumps(notify_payload))

        try:
            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Rider Assigned",
                f"{user.name} is on the way!"
            )
            await manager.send_notification(
                "vendors",
                str(vendor.user_id),
                "Rider Assigned",
                f"Rider {user.name} assigned to order {order_id}"
            )
        except Exception as e:
            logger.warning(f"WebSocket notification failed: {str(e)}")

        # Send push notifications
        try:
            await send_notification(
                order.user_id,
                "Rider Assigned",
                f"Rider {user.name} is on the way!"
            )

            await send_notification(
                vendor.user_id,
                "Order Confirmed",
                f"Order {order_id} confirmed with rider {user.name}"
            )
        except Exception as e:
            logger.error(f"Push notification error: {str(e)}")

        # Start chat channels
        customer_message = None
        vendor_message = None
        location_subscribe = None

        try:
            customer_message = await start_chat("riders", user.id, "customers", order.user_id)
            vendor_message = await start_chat("riders", user.id, "vendors", vendor.user_id)
            location_subscribe = await subscribe_to_riders_location("subscribe", user.id, order.user_id)
        except Exception as e:
            logger.error(f"Chat initialization error: {str(e)}")

        # Clean up Redis claim
        await redis.delete(claim_key)

        return translate({
            "status": "order_accepted",
            "order_id": order_id,
            "rider_id": rider_profile.user_id,
            "payout": float(order.base_rate + order.distance_bonus),
            "base_rate": float(order.base_rate),
            "distance_bonus": float(order.distance_bonus),
            "eta_minutes": order.eta_minutes,
            "customer_message": customer_message,
            "vendor_message": vendor_message,
            "location_subscribe": location_subscribe
        }, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/reject/{order_id}/")
async def reject_order(
    request: Request,
    order_id: str,
    reason: str = Form(...),
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    RIDER rejects an order.
    
    For URGENT orders: reason is mandatory and tracked.
    For other orders: reason is optional but recommended.
    
    Updates:
    - OrderOffer status to REJECTED
    - WorkDay rejection count
    - Logs rejection for audit trail
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    try:
        rider = await RiderProfile.get_or_none(user=user)
        if not rider:
            raise HTTPException(status_code=403, detail="Not a rider")

        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Check if order is still in PROCESSING
        if order.status != OrderStatus.PROCESSING:
            raise HTTPException(status_code=400, detail="Order not available for rejection")

        is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT

        # For urgent orders, reason is required
        if is_urgent and not reason.strip():
            raise HTTPException(status_code=400, detail="Reason is required for urgent order rejection")

        # Get the most recent offer for this rider
        offer = await OrderOffer.filter(
            order=order,
            rider=rider
        ).order_by("-created_at").first()

        if not offer:
            raise HTTPException(status_code=400, detail="No active offer for this order")

        if offer.status != "PENDING":
            raise HTTPException(status_code=400, detail="Offer already responded to")

        # Update offer
        offer.status = "REJECTED"
        offer.reject_reason = reason
        offer.responded_at = datetime.utcnow()
        await offer.save()

        # Update WorkDay stats
        today = date.today()
        workday, _ = await WorkDay.get_or_create(
            rider=rider,
            date=today,
            defaults={"hours_worked": 0.0, "order_offer_count": 0, "rejection_count": 0}
        )
        if not hasattr(workday, 'rejection_count'):
            workday.rejection_count = 0
        workday.rejection_count += 1
        await workday.save()

        logger.info(f"Order {order_id} rejected by rider {rider.id}. Reason: {reason}")

        return translate({
            "status": "rejected",
            "order_id": order_id,
            "reason": reason,
            "is_urgent": is_urgent
        }, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/shipped/{order_id}/")
async def mark_order_shipped(
    request: Request,
    order_id: str,
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    VENDOR marks order as shipped (picked up by rider).
    Flow: CONFIRMED -> SHIPPED
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_vendor:
        raise HTTPException(status_code=403, detail="Only vendors can mark shipped")

    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != OrderStatus.CONFIRMED:
            raise HTTPException(status_code=400, detail="Order must be confirmed first")

        order.status = OrderStatus.SHIPPED
        order.shipped_at = datetime.utcnow()
        await order.save()

        notify_payload = {
            "type": "order_shipped",
            "order_id": order_id,
            "shipped_at": datetime.utcnow().isoformat()
        }

        await redis.publish("order_updates", json.dumps(notify_payload))

        try:
            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Order Picked Up",
                "Your order has been picked up!"
            )
            await send_notification(order.user_id, "Order Shipped", "Your order is on the way!")
        except Exception as e:
            logger.warning(f"Shipment notification error: {str(e)}")

        return translate({"status": "shipped", "order_id": order_id}, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking shipped: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/out-for-delivery/{order_id}/")
async def mark_order_out_for_delivery(
    request: Request,
    order_id: str,
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    RIDER marks order as out for delivery.
    Flow: SHIPPED -> OUT_FOR_DELIVERY
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_rider:
        raise HTTPException(status_code=403, detail="Only riders can update this")

    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != OrderStatus.SHIPPED:
            raise HTTPException(status_code=400, detail="Order not in shipped status")

        order.status = OrderStatus.OUT_FOR_DELIVERY
        order.out_for_delivery_at = datetime.utcnow()
        await order.save()

        notify_payload = {
            "type": "order_out_for_delivery",
            "order_id": order_id,
            "out_for_delivery_at": datetime.utcnow().isoformat()
        }

        await redis.publish("order_updates", json.dumps(notify_payload))

        try:
            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Out for Delivery",
                "Your order is arriving soon!"
            )
            await send_notification(order.user_id, "Out for Delivery", "Your order is on its way!")
        except Exception as e:
            logger.warning(f"Out for delivery notification error: {str(e)}")

        return translate({"status": "out_for_delivery", "order_id": order_id}, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking out for delivery: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/delivered/{order_id}/")
async def mark_order_delivered(
    request: Request,
    order_id: str,
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    RIDER marks order as delivered.
    Flow: OUT_FOR_DELIVERY -> DELIVERED
    
    - Check if on-time delivery
    - Update rider balance
    - Send notifications
    - End chat sessions
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_rider:
        raise HTTPException(status_code=403, detail="Only riders can mark delivered")

    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(status_code=404, detail="Order item not found")

        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        if order.status != OrderStatus.OUT_FOR_DELIVERY:
            raise HTTPException(status_code=400, detail="Order not out for delivery")

        # Check if on-time
        now = datetime.now(timezone.utc)
        accepted_at = to_utc(order.accepted_at)

        if accepted_at and order.eta_minutes:
            eta_deadline = accepted_at + timedelta(minutes=order.eta_minutes)
            order.is_on_time = now <= eta_deadline
        else:
            order.is_on_time = True

        # Update order
        order.status = OrderStatus.DELIVERED
        order.completed_at = now
        await order.save()

        # Update rider balance
        rider = await RiderProfile.get_or_none(id=order.rider_id)
        if rider:
            payout = float(order.base_rate or 0) + float(order.distance_bonus or 0)
            rider.current_balance += Decimal(str(payout))
            await rider.save()
            logger.info(f"Rider {rider.id} balance updated: +₹{payout}")

        # Add money to vendor account
        try:
            await add_money_to_vendor_account(order.id)
        except Exception as e:
            logger.warning(f"Error adding money to vendor account: {str(e)}")

        # Send notifications
        notify_payload = {
            "type": "order_delivered",
            "order_id": order_id,
            "delivered_at": now.isoformat(),
            "is_on_time": order.is_on_time,
            "payout": float(order.base_rate or 0) + float(order.distance_bonus or 0)
        }

        await redis.publish("order_updates", json.dumps(notify_payload))

        try:
            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Order Delivered",
                "Thank you for your order!"
            )
            await manager.send_notification(
                "vendors",
                str(vendor.user_id),
                "Order Delivered",
                f"Order {order_id} delivered successfully!"
            )
            await send_notification(order.user_id, "Order Delivered", "Thank you for your order!")
        except Exception as e:
            logger.warning(f"Delivery notification error: {str(e)}")

        # End chat
        try:
            await end_chat("riders", user.id, "customers", order.user_id)
            await end_chat("riders", user.id, "vendors", vendor.user_id)
            await subscribe_to_riders_location("unsubscribe", user.id, order.user_id)
        except Exception as e:
            logger.warning(f"Chat cleanup error: {str(e)}")

        return translate({
            "status": "delivered",
            "order_id": order_id,
            "is_on_time": order.is_on_time,
            "payout": float(order.base_rate or 0) + float(order.distance_bonus or 0)
        }, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking delivered: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/orders/cancel/{order_id}/")
async def cancel_order(
    request: Request,
    order_id: str,
    reason: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    redis=Depends(get_redis)
):
    """
    Cancel an order.
    Cannot cancel if already delivered or previously cancelled.
    Restores item stock.
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(status_code=404, detail="Order item not found")

        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        # Cannot cancel if already delivered or cancelled
        if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
            raise HTTPException(status_code=400, detail="Order cannot be cancelled")

        order.status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        order.cancelled_at = datetime.utcnow()
        await order.save()

        # Restore stock
        item.stock += order_item.quantity
        await item.save()

        notify_payload = {
            "type": "order_cancelled",
            "order_id": order_id,
            "cancelled_at": datetime.utcnow().isoformat(),
            "reason": reason
        }

        await redis.publish("order_updates", json.dumps(notify_payload))

        try:
            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Order Cancelled",
                f"Reason: {reason or 'Not specified'}"
            )
            await manager.send_notification(
                "vendors",
                str(vendor.user_id),
                "Order Cancelled",
                f"Order {order_id} has been cancelled"
            )
            await send_notification(order.user_id, "Order Cancelled", f"Reason: {reason or 'Not specified'}")
        except Exception as e:
            logger.warning(f"Cancellation notification error: {str(e)}")

        try:
            rider = await RiderProfile.get_or_none(id=order.rider_id)
            if rider:
                await end_chat("riders", rider.user_id, "customers", order.user_id)
                await end_chat("riders", rider.user_id, "vendors", vendor.user_id)
                await subscribe_to_riders_location("unsubscribe", rider.user_id, order.user_id)
        except Exception as e:
            logger.warning(f"Chat cleanup error: {str(e)}")

        return translate({"status": "cancelled", "order_id": order_id}, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/orders/{order_id}/")
async def get_order_details(
    request: Request,
    order_id: str,
    user: User = Depends(get_current_user),
):
    """
    Get detailed information about an order.
    Includes rider, vendor, customer, payout, and delivery status.
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # rider = None
        # rider_name = None
        # if order.rider_id:
        #     rider = await RiderProfile.get_or_none(id=order.rider_id)
        #     if rider and rider.user:
        #         rider_name = rider.user.name

        # order_item = await OrderItem.get_or_none(order=order)
        # if not order_item:
        #     raise HTTPException(status_code=404, detail="Order item not found")

        # item = await Item.get_or_none(id=order_item.item_id)
        # if not item:
        #     raise HTTPException(status_code=404, detail="Item not found")

        # vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        # if not vendor:
        #     raise HTTPException(status_code=404, detail="Vendor not found")
        

        return await OrderOut.from_tortoise_orm(translate(order, lang))

        # return translate({
        #     "id": order.id,
        #     "status": str(order.status),
        #     "delivery_type": str(order.delivery_type),
        #     "rider_id": rider.user_id if rider else None,
        #     "rider_name": rider_name,
        #     "vendor_id": vendor.user_id,
        #     "customer_id": order.user_id,
        #     "base_rate": float(order.base_rate or 0),
        #     "distance_bonus": float(order.distance_bonus or 0),
        #     "total_payout": float((order.base_rate or 0) + (order.distance_bonus or 0)),
        #     "eta_minutes": order.eta_minutes,
        #     "is_on_time": order.is_on_time,
        #     "is_combined": order.is_combined,
        #     "combined_pickups": order.combined_pickups,
        #     "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
        #     "completed_at": order.completed_at.isoformat() if order.completed_at else None
        # }, lang)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order details: {str(e)}")
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
        ).offset(skip).limit(limit).order_by("-created_at").all()



        return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    

@router.get("/current-orders/")
async def current_orders_list(
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
            rider=rider, status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
        ).offset(skip).limit(limit).order_by("-created_at").all()



        return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    




@router.get("/offered-orders/")
async def list_orders_offer(
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
            rider=None, metadata__contains={"candidate_riders": [rider.id]}, status=OrderStatus.CONFIRMED
        ).offset(skip).limit(limit).order_by("-created_at").all()



        return [await OrderOut.from_tortoise_orm(translate(order, lang)) for order in orders]


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


