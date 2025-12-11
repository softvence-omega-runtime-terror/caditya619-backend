# from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form
# from datetime import date, datetime, time, timedelta
# from applications.user.models import User
# from enum import Enum
# from app.token import get_current_user
# from applications.user.rider import RiderProfile, OrderOffer, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses
# from app.utils.file_manager import save_file, update_file, delete_file
# from tortoise.exceptions import IntegrityError
# from tortoise.contrib.pydantic import pydantic_model_creator
# from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
# from applications.items.models import Item
# from applications.user.vendor import VendorProfile
# from applications.user.customer import CustomerProfile
# import uuid
# from app.utils.geo import haversine, bbox_for_radius, estimate_eta
# import json
# from app.utils.websocket_manager import manager
# from tortoise.transactions import in_transaction
# #from helper_functions import start_chat, end_chat
# from .helper_functions import start_chat, end_chat
# from starlette.websockets import WebSocketDisconnect, WebSocket
# import asyncio
# # from app.utils.map_distance_ETA import haversine, estimate_eta
# # from fastapi.responses import HTMLResponse
# from app.redis import get_redis
# #from fastapi.background import BackgroundTasks
# import logging
# from datetime import timezone
# from .notifications import send_notification





# from passlib.context import CryptContext
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# router = APIRouter(tags=['Rider Orders'])



# OFFER_TIMEOUT_SECONDS = 1200
# GEO_REDIS_KEY = "riders_geo"
# INITIAL_RADIUS_KM = 5.0
# RADIUS_STEP_KM = 5.0
# MAX_RADIUS_KM = 20.0


# # Add expires_at to OrderOffer if not
# # expires_at = fields.DatetimeField(null=True)

# # Add to WorkDay if needed: orders_accepted = fields.IntField(default=0)



# logger = logging.getLogger(__name__)

# async def notify_rider(rider_id: int,order: "Order"):
#     payload = {
#         "type": "order_offer",
#         "order_id": order.id
#     }
#     rider = await RiderProfile.get_or_none(id=rider_id)
#     redis = get_redis()  # Assume this works; in prod, consider pooling or injecting
#     await redis.publish("order_offers", json.dumps(payload))
#     print(f"user id is {rider.user_id}")
#     await manager.send_to(payload, "riders", str(rider.user_id))
#     try:
#         await send_notification(rider.user_id, "New Order Offer", f"You have a new order offer: {order.id}")
#     except Exception as e:
#         logger.error(f"Failed to send notification to rider {rider_id}: {str(e)}")


# async def offer_sequential(order_id: str, prepire_time: int):
#     try:
#         order = await Order.get_or_none(id=order_id)
#         if not order:
#             logger.error(f"Order {order_id} not found for sequential offering")
#             return
#         candidates = order.metadata.get("candidate_riders", [])
#         if candidates:
#             order.status = OrderStatus.PROCESSING
#             order.prepire_time = prepire_time
#             await order.save()
            
#         for i, rider_id in enumerate(candidates):
#             rider = await RiderProfile.get_or_none(id=rider_id)
#             if not rider:
#                 continue
#             if order.status != OrderStatus.PROCESSING:
#                 break
#             await notify_rider(rider_id, order)
#             today = date.today()
#             workday, _ = await WorkDay.get_or_create(rider=rider, date=today, defaults={"hours_worked": 0.0, "orders_accepted": 0})
#             workday.order_offer_count += 1
#             await workday.save()
#             #await asyncio.sleep(OFFER_TIMEOUT_SECONDS)
#             if order.status != OrderStatus.PROCESSING:
#                 break
#     except Exception as e:
#         logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")








# @router.post("/order-offers/{order_id}/", status_code=201)
# async def create_order(
#     order_id: str,
#     background_tasks: BackgroundTasks,
#     prepire_time: int = Form(),
#     top_n: int = 20,
#     current_user = Depends(get_current_user),
#     redis = Depends(get_redis)
# ):
#     if not current_user.is_vendor:
#         raise HTTPException(status_code=403, detail="User type is not vendor")
#     if top_n <= 0:
#         raise HTTPException(status_code=400, detail="Invalid parameters")
#     order = await Order.get_or_none(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     order_item = await OrderItem.get_or_none(order=order)
#     if not order_item:
#         raise HTTPException(404, "Order item not found")
    
#     item = await Item.get_or_none(id=order_item.item_id)
#     if not item:
#         raise HTTPException(404, "Item not found")
#     vendor = await VendorProfile.get_or_none(id=item.vendor_id)
#     if not vendor:
#         raise HTTPException(404, "Vendor not found")
#     # customer = await CustomerProfile.get_or_none(id=order.user_id)
#     # if not customer:
#     #     raise HTTPException(404, "Customer not found")

#     # Add vendor_lat etc to order if needed
#     order.status = OrderStatus.PENDING
#     await order.save()
#     print(f"order current status is {order.status}")
#     candidates = []
#     radius = INITIAL_RADIUS_KM
#     existing_ids = set()
#     while len(candidates) < top_n and radius <= MAX_RADIUS_KM:
#         candidate_rider_ids = []
#         try:
#             geo_res = await redis.execute_command(
#                 "GEOSEARCH", GEO_REDIS_KEY,
#                 "FROMLONLAT", vendor.latitude, vendor.longitude,
#                 "BYRADIUS", radius, "km",
#                 "ASC",
#                 "COUNT", top_n * 3
#             )
#             candidate_rider_ids = [int(x) for x in geo_res if int(x) not in existing_ids]
#         except Exception:
#             pass
#         temp_candidates = []
#         if candidate_rider_ids:
#             riders = await RiderProfile.filter(id__in=candidate_rider_ids, is_available=True).prefetch_related("current_location").all()
#             id_to_idx = {rid: i for i, rid in enumerate(candidate_rider_ids)}
#             riders.sort(key=lambda r: id_to_idx.get(r.id, 9999))
#             for r in riders:
#                 loc = r.current_location
#                 if not loc:
#                     continue
#                 dist = haversine(vendor.latitude, vendor.longitude, loc.latitude, loc.longitude)
#                 if dist <= radius:
#                     temp_candidates.append((r, dist))
#                     existing_ids.add(r.id)
#         else:
#             lat_min, lat_max, lng_min, lng_max = bbox_for_radius(vendor.latitude, vendor.longitude, radius)
#             riders = await RiderProfile.filter(is_available=True).prefetch_related("current_location").all()
#             for r in riders:
#                 if r.id in existing_ids:
#                     continue
#                 loc = r.current_location
#                 if not loc:
#                     continue
#                 if not (lat_min <= loc.latitude <= lat_max and lng_min <= loc.longitude <= lng_max):
#                     continue
#                 dist = haversine(vendor.latitude, vendor.longitude, loc.latitude, loc.longitude)
#                 if dist <= radius:
#                     temp_candidates.append((r, dist))
#                     existing_ids.add(r.id)
#         candidates.extend(temp_candidates)
#         candidates.sort(key=lambda x: x[1])
#         candidates = candidates[:top_n]
#         radius += RADIUS_STEP_KM
#     if not candidates:
#         raise HTTPException(status_code=400, detail="No riders available")
#     chosen = [c[0] for c in candidates]
#     order.metadata = order.metadata or {}
#     order.metadata["candidate_riders"] = [r.id for r in chosen]
#     await order.save()
#     # For background async
#     background_tasks.add_task(offer_sequential, order_id, prepire_time)  # Assume setup for async background
#     return {"order_id": order.id, "potential_offers": len(chosen)}






# @router.post("/orders/accept/{order_id}/")
# async def accept_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
#     rider_profile = await RiderProfile.filter(user=user).first()
#     if not rider_profile:
#         raise HTTPException(403, "Not a rider")
#     claim_key = f"order_claim:{order_id}"
#     claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)
#     if not claimed:
#         raise HTTPException(status_code=400, detail="Order already claimed")
#     order = await Order.get(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     # now = datetime.now(timezone.utc)
#     # if order.expires_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
#     #     print(f"expires at is {order.expires_at} and now is {now}")
#     #     await redis.delete(claim_key)
#     #     raise HTTPException(400, "Offer expired")
#     async with in_transaction() as conn:
#         # order = await Order.get(id=order_id).using_db(conn)
#         if order.status != OrderStatus.PROCESSING:
#             await redis.delete(claim_key)
#             raise HTTPException(status_code=400, detail="Order not available")
#         order.status = OrderStatus.CONFIRMED
#         order.rider = rider_profile

#         customer = await CustomerProfile.get_or_none(id=order.user_id)
#         if not customer:
#             raise HTTPException(404, "Customer not found")
        

#         loc = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
#         if not loc:
#             raise HTTPException(400, "Rider location not found")
#         order_item = await OrderItem.get_or_none(order=order)
#         if not order_item:
#             raise HTTPException(404, "Order item not found")
        
#         item = await Item.get_or_none(id=order_item.item_id)
#         if not item:
#             raise HTTPException(404, "Item not found")
#         vendor = await VendorProfile.get_or_none(id=item.vendor_id)
#         if not vendor:
#             raise HTTPException(404, "Vendor not found")
#         vendor_lat = vendor.latitude
#         vendor_lng = vendor.longitude
#         dist1 = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
#         dist2 = haversine(loc.latitude, loc.longitude, customer.customer_lat, customer.customer_lng)
#         feesandbonus = await RiderFeesAndBonuses.get(id = 1)
#         if not feesandbonus:
#             raise HTTPException(status_code=500, detail="Rider fees and bonuses not configured")
#         pickup_time = datetime.utcnow() + timedelta(minutes=10)  # estimate
#         eta_minutes = int(estimate_eta(dist1).total_seconds() / 60) + int(estimate_eta(dist2).total_seconds() / 60) + order.prepire_time
#         base_rate = feesandbonus.rider_delivery_fee or 44.00
#         distance_bonus = max((dist1+dist2) - 3, 0) * (feesandbonus.distance_bonus_per_km or 1.0)
#         expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
        
#         order.pickup_distance_km = dist1
#         order.pickup_time = pickup_time
#         order.eta_minutes = eta_minutes
#         order.base_rate = base_rate
#         order.distance_bonus = distance_bonus
#         order.offered_at = datetime.utcnow()
#         order.expires_at = expires_at
#         order.metadata = order.metadata or {}
#         order.metadata["rider_id"] = rider_profile.id
#         # await order.save(using_db=conn)
#         order.accepted_at = datetime.utcnow()
#         await order.save(using_db=conn)
#         # Reject others if any
#         await OrderOffer.filter(order=order).exclude(rider=rider_profile).update(status="rejected", responded_at=datetime.utcnow())
   
#     notify_payload = {
#         "type": "order_accepted",
#         "order_id": order_id,
#         "rider_id": rider_profile.id,
#         "accepted_at": datetime.utcnow().isoformat()
#     }
#     await redis.publish("order_updates", json.dumps(notify_payload))
#     try:
#         await manager.send_to(notify_payload, "customers", str(order.user_id))
#         await manager.send_to(notify_payload, "vendors", str(vendor.user_id))
#     except:
#         pass
#     try:
#         await send_notification(order.user_id, "Order Accepted", f"Your order {order.id} has been accepted by a {rider_profile.user.name}.")
#         await send_notification(vendor.user_id, "Order Accepted", f"Order {order.id} has been accepted by rider {rider_profile.user.name}.")
#     except Exception as e:
#         logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")
#     customer_message = start_chat("riders", user.id, "customers", order.user_id)
#     vendor_message = start_chat("riders", user.id, "vendors", vendor.user_id)
#     await redis.delete(claim_key)
#     return {"status": "accepted", "order_id": order_id, "rider_id": rider_profile.id, "customer_message": customer_message, "vendor_message": vendor_message}






# @router.post("/orders/shipped/{order_id}/")
# async def mark_order_shipped(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):

#     if not user.is_vendor:
#         raise HTTPException(403, "User is not a vendor")
#     order = await Order.get_or_none(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     if order.status != OrderStatus.CONFIRMED:
#         raise HTTPException(400, "Order not in confirmed status")
#     order.status = OrderStatus.SHIPPED
#     await order.save()
#     offer = await OrderOffer.filter(order_id=order_id).first()
#     notify_payload = {
#         "type": "order_shipped",
#         "order_id": order_id,
#         "shipped_at": datetime.utcnow().isoformat()
#     }
#     await redis.publish("order_updates", json.dumps(notify_payload))
#     try:
#         await manager.send_to(notify_payload, "customers", str(order.user_id))
#     except:
#         pass

#     try:
#         await send_notification(order.user_id, "Order Shipped", f"Your order {order.id} has been shipped and is on its way!")
#     except Exception as e:
#         logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")

#     return {"status": "shipped", "order_id": order_id, "rider_id": offer.rider_id}






# @router.post("/orders/out-for-delivery/{order_id}/")
# async def mark_order_out_for_delivery(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
#     if not user.is_rider:
#         raise HTTPException(403, "User is not a valid rider")
#     order = await Order.get_or_none(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     if order.status != OrderStatus.SHIPPED:
#         raise HTTPException(400, "Order not in shipped status")
#     order.status = OrderStatus.OUT_FOR_DELIVERY
#     await order.save()
#     notify_payload = {
#         "type": "order_out_for_delivery",
#         "order_id": order_id,
#         "out_for_delivery_at": datetime.utcnow().isoformat()
#     }
#     await redis.publish("order_updates", json.dumps(notify_payload))
#     try:
#         await manager.send_to(notify_payload, "customers", str(order.user_id))
#     except:
#         pass
#     try:
#         await send_notification(order.user_id, "Order Out for Delivery", f"Your order {order.id} is out for delivery!")
#     except Exception as e:
#         logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")

#     return {"status": "out_for_delivery", "order_id": order_id, "rider_id": order.rider_id}




# @router.post("/orders/delivered/{order_id}/")
# async def mark_order_delivered(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
#     if not user.is_rider:
#         raise HTTPException(403, "User is not a valid rider")
    
#     order = await Order.get_or_none(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     order_item = await OrderItem.get_or_none(order=order)
#     if not order_item:
#         raise HTTPException(404, "Order item not found")
    
#     item = await Item.get_or_none(id=order_item.item_id)
#     if not item:
#         raise HTTPException(404, "Item not found")
#     vendor = await VendorProfile.get_or_none(id=item.vendor_id)
#     if not vendor:
#         raise HTTPException(404, "Vendor not found")
#     rider = await RiderProfile.get_or_none(id=order.rider_id)
#     if not rider:
#         raise HTTPException(404, "Rider not found")

#     if order.status != OrderStatus.OUT_FOR_DELIVERY:
#         raise HTTPException(400, "Order not in out for delivery status")
#     duration_sec = (order.completed_at - order.accepted_at).total_seconds()
#     if duration_sec <= order.eta_minutes*60:
#         order.is_on_time = True
#     order.status = OrderStatus.DELIVERED
#     order.completed_at = datetime.utcnow()
#     await order.save()
#     rider.current_balance += order.base_rate + order.distance_bonus
#     await rider.save()
#     notify_payload = {
#         "type": "order_delivered",
#         "order_id": order_id,
#         "delivered_at": datetime.utcnow().isoformat()
#     }
#     await redis.publish("order_updates", json.dumps(notify_payload))
#     try:
#         await manager.send_to(notify_payload, "customers", str(order.user_id))
#         await manager.send_to(notify_payload, "vendors", str(vendor.user_id))
#     except:
#         pass
#     try:
#         await send_notification(order.user_id, "Order Delivered", f"Your order {order.id} has been delivered successfully!")
#         await send_notification(vendor.user_id, "Order Delivered", f"Order {order.id} has been delivered.")
#     except Exception as e:
#         logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")

#     end_chat("riders", user.id, "customers", order.user_id)
#     end_chat("riders", user.id, "vendors", vendor.user_id)
#     return {"status": "delivered", "order_id": order_id, "rider_id": order.rider_id}




# @router.post("/orders/cancel/{order_id}/")
# async def cancel_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
#     order = await Order.get_or_none(id=order_id)
#     if not order:
#         raise HTTPException(404, "Order not found")
#     if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
#         raise HTTPException(400, "Order cannot be cancelled")
#     order.status = OrderStatus.CANCELLED
#     await order.save()
#     notify_payload = {
#         "type": "order_cancelled",
#         "order_id": order_id,
#         "cancelled_at": datetime.utcnow().isoformat()
#     }
#     await redis.publish("order_updates", json.dumps(notify_payload))
#     try:
#         await manager.send_to(notify_payload, "customers", str(order.user_id))
#     except:
#         pass
#     try:
#         await send_notification(order.user_id, "Order Cancelled", f"Your order {order.id} has been cancelled.")
#     except Exception as e:
#         logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")
#     return {"status": "cancelled", "order_id": order_id}






from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import json
import asyncio

from applications.user.models import User
from applications.user.rider import (
    RiderProfile, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses
)
from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
from applications.items.models import Item
from applications.user.vendor import VendorProfile
from applications.user.customer import CustomerProfile
from applications.earning.vendor_earning import add_money_to_vendor_account
from app.token import get_current_user
from app.utils.geo import haversine, bbox_for_radius, estimate_eta
from app.utils.websocket_manager import manager
from app.redis import get_redis
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError

from .notifications import send_notification
from .websocket_endpoints import start_chat, end_chat, subscribe_to_riders_location

logger = logging.getLogger(__name__)

# Configuration constants
OFFER_TIMEOUT_SECONDS = 1200  # 20 minutes
GEO_REDIS_KEY = "riders_geo"
INITIAL_RADIUS_KM = 3.0
RADIUS_STEP_KM = 1.0
MAX_RADIUS_KM = 20.0
URGENT_RADIUS_KM = 10.0  # Urgent orders search in 10km radius

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class OrderAcceptRequest(BaseModel):
    order_id: str
    reason: Optional[str] = None

class OrderRejectRequest(BaseModel):
    order_id: str
    reason: str

class OrderStatusUpdate(BaseModel):
    order_id: str
    status: str
    notes: Optional[str] = None

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(tags=['Rider Orders'])

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def notify_rider_websocket(rider_id: int, order: Order, notification_type: str = "order_offer"):
    """Send notification via WebSocket"""
    try:
        payload = {
            "type": notification_type,
            "order_id": str(order.id),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        rider = await RiderProfile.get_or_none(id=rider_id)
        if rider:
            print("Sending websocket notification")
            success = await manager.send_notification("riders", str(rider.user_id), "New Order Offer", f"You have received a new order offer! order id {order.id}")
            logger.info(f"WebSocket notification sent to rider {rider_id}")
    except Exception as e:
        logger.error(f"WebSocket notification error for rider {rider_id}: {str(e)}")

async def notify_rider_pushnotification(rider_id: int, title: str, body: str):
    """Send push notification"""
    try:
        rider = await RiderProfile.get_or_none(id=rider_id)
        if rider and rider.user_id:
            await send_notification(rider.user_id, title, body)
            logger.info(f"Push notification sent to rider {rider_id}")
    except Exception as e:
        logger.error(f"Push notification error for rider {rider_id}: {str(e)}")

async def find_candidate_riders(
    vendor_lat: float,
    vendor_lng: float,
    is_urgent: bool = False,
    top_n: int = 20,
    redis = None
) -> List[RiderProfile]:
    """
    Find eligible rider candidates based on location and availability
    Strategy: Nearest available riders first, expanding radius if needed
    """
    candidates = []
    radius = URGENT_RADIUS_KM if is_urgent else INITIAL_RADIUS_KM
    max_radius = URGENT_RADIUS_KM if is_urgent else MAX_RADIUS_KM
    existing_ids = set()
    
    while len(candidates) < top_n and radius <= max_radius:
        try:
            # Try Redis GEO search first
            if redis:
                try:
                    geo_res = await redis.execute_command(
                        "GEOSEARCH", GEO_REDIS_KEY,
                        "FROMLONLAT", vendor_lng, vendor_lat,
                        "BYRADIUS", radius, "km",
                        "ASC",
                        "COUNT", top_n * 3
                    )
                    
                    candidate_rider_ids = [
                        int(x) for x in geo_res
                        if int(x) not in existing_ids
                    ]
                except Exception as e:
                    logger.warning(f"Redis GEO search failed: {str(e)}")
                    candidate_rider_ids = []
            else:
                candidate_rider_ids = []
            
            # Get riders from database
            riders = await RiderProfile.filter(
                id__in=candidate_rider_ids if candidate_rider_ids else [],
                is_available=True
            ).prefetch_related("current_location").all()
            
            # If no Redis results, query all available riders
            if not riders:
                riders = await RiderProfile.filter(
                    is_available=True
                ).prefetch_related("current_location").all()
            
            # Calculate distance and sort
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
            
            # Sort by distance
            rider_distances.sort(key=lambda x: x[1])
            candidates.extend(rider_distances)
            
        except Exception as e:
            logger.error(f"Error finding candidates at radius {radius}km: {str(e)}")
        
        radius += RADIUS_STEP_KM
    
    # Remove duplicates and return limited list
    seen_ids = set()
    result = []
    for rider, _ in candidates:
        if rider.id not in seen_ids:
            result.append(rider)
            seen_ids.add(rider.id)
            if len(result) >= top_n:
                break
    
    return result

async def offer_order_sequentially(
    order_id: str,
    candidate_riders: List[RiderProfile],
    background_tasks: BackgroundTasks
):
    """
    Offer order to riders sequentially with timeout
    - First rider to accept gets the order
    - If rejected/timeout, move to next rider
    """
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            return
        
        # Try each rider sequentially
        for idx, rider in enumerate(candidate_riders):
            if order.status != OrderStatus.PROCESSING:
                # Order already accepted by another rider
                logger.info(f"Order {order_id} already taken, stopping offers")
                break
            
            try:
                # Send notification
                await notify_rider_websocket(rider.id, order, "order_offer")
                
                # Check if order type is urgent
                is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
                notification_title = "🚨 URGENT: Medicine Delivery" if is_urgent else "New Order Offer"
                notification_body = f"Order {order.id} - Payout: ₹{order.base_rate + order.distance_bonus}"
                
                await notify_rider_pushnotification(rider.id, notification_title, notification_body)
                
                # Update work day
                today = date.today()
                workday, _ = await WorkDay.get_or_create(
                    rider=rider,
                    date=today,
                    defaults={"hours_worked": 0.0, "order_offer_count": 0}
                )
                workday.order_offer_count += 1
                await workday.save()
                
                logger.info(f"Order {order_id} offered to rider {rider.id} ({idx + 1}/{len(candidate_riders)})")
                
            except Exception as e:
                logger.error(f"Error offering order to rider {rider.id}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")

# ============================================================================
# ORDER ENDPOINTS
# ============================================================================

@router.post("/orders/create-offer/{order_id}/")
async def create_order_offer(
    order_id: str,
    background_tasks: BackgroundTasks,
    prepare_time: int = Form(...),
    top_n: int = 20,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    Create order offer and find eligible riders
    Called by VENDOR after order is placed
    
    Flow:
    1. Find candidate riders based on location
    2. Validate order details
    3. Send offers to riders sequentially
    """
    
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="Only vendors can create offers")
    
    if top_n <= 0 or top_n > 100:
        raise HTTPException(status_code=400, detail="Invalid top_n parameter")
    
    try:
        # Get order
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Get order item
        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(status_code=404, detail="Order item not found")
        
        # Get item and vendor
        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        # Get customer
        customer = await CustomerProfile.get_or_none(id=order.user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Validate order is not already processed
        if order.status not in [OrderStatus.PROCESSING]:
            raise HTTPException(status_code=400, detail="Order already being processed")
        
        # Check if urgent order
        is_urgent = order.delivery_type == DeliveryTypeEnum.URGENT
        
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
        
        # Update order status
        order.status = OrderStatus.CONFIRMED
        order.metadata = order.metadata or {}
        order.metadata["candidate_riders"] = [r.id for r in candidates]
        order.metadata["offered_at"] = datetime.utcnow().isoformat()
        order.prepare_time = prepare_time
        await order.save()
        
        # Queue sequential offering in background
        background_tasks.add_task(
            offer_order_sequentially,
            order_id,
            candidates,
            background_tasks
        )
        
        return {
            "status": "offer_created",
            "order_id": order_id,
            "candidate_count": len(candidates),
            "is_urgent": is_urgent,
            "message": "Order offers sent to nearby riders"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order offer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/orders/accept/{order_id}/")
async def accept_order(
    order_id: str,
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    RIDER accepts an order
    
    Flow:
    1. Claim order (race condition prevention)
    2. Validate order status
    3. Calculate payout
    4. Update order and rider balance
    5. Notify customer and vendor
    6. Start chat channels
    """
    
    try:
        # Get rider profile
        rider_profile = await RiderProfile.get_or_none(user=user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider profile")
        
        # Prevent race condition with Redis claim
        claim_key = f"order_claim:{order_id}"
        claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)
        
        if not claimed:
            raise HTTPException(status_code=400, detail="Order already claimed by another rider")
        
        # Get order
        order = await Order.get_or_none(id=order_id)
        if not order:
            await redis.delete(claim_key)
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Validate order status
        if order.status != OrderStatus.CONFIRMED:
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available (already accepted)")
        
        # Check for split/urgent restrictions
        if order.delivery_type == DeliveryTypeEnum.SPLIT:
            # Split orders: rider cannot accept another order until delivered
            active_split = await Order.filter(
                rider=rider_profile,
                delivery_type=DeliveryTypeEnum.SPLIT,
                status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
            ).first()
            
            if active_split:
                await redis.delete(claim_key)
                raise HTTPException(
                    status_code=400,
                    detail="Cannot accept another split order until current delivery is complete"
                )
        
        async with in_transaction():
            # Verify order still available
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
            if order.is_combined and order.combined_pickups:
                base_rate += (len(order.combined_pickups) - 1) * base_rate
            
            # Estimate ETA
            pickup_eta_min = int(estimate_eta(pickup_dist).total_seconds() / 60)
            delivery_eta_min = int(estimate_eta(delivery_dist).total_seconds() / 60)
            eta_minutes = pickup_eta_min + delivery_eta_min + (order.prepare_time or 10)
            
            # Update order
            #order.status = OrderStatus.CONFIRMED
            order.rider = rider_profile
            order.pickup_distance_km = pickup_dist
            order.base_rate = Decimal(str(base_rate))
            order.distance_bonus = Decimal(str(round(distance_bonus, 2)))
            order.eta_minutes = eta_minutes
            order.accepted_at = datetime.utcnow()
            order.expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
            order.metadata = order.metadata or {}
            order.metadata["rider_id"] = rider_profile.id
            
            await order.save()
            
        
        # Send notifications via WebSocket
        notify_payload = {
            "type": "order_accepted",
            "order_id": order_id,
            "rider_id": rider_profile.id,
            "rider_name": user.name,
            "accepted_at": datetime.utcnow().isoformat()
        }
        
        await redis.publish("order_updates", json.dumps(notify_payload))
        
        try:
            await manager.send_notification("customers", str(order.user_id), "Rider assigned", "{user.name} is assigned for order {order_id}")
            await manager.send_notification("vendors", str(vendor.user_id), "Rider assigned", "{user.name} is assigned for order {order_id}")
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
        
        # Start chat
        try:
            customer_message = await start_chat("riders", user.id, "customers", order.user_id)
            vendor_message = await start_chat("riders", user.id, "vendors", vendor.user_id)
            locatin_subscribe = subscribe_to_riders_location(rider_profile.user_id, order.user_id, "subscribe")
        except Exception as e:
            logger.error(f"Chat initialization error: {str(e)}")
            customer_message = vendor_message = None
        
        # Clean up Redis claim
        await redis.delete(claim_key)
        
        return {
            "status": "rider assigned",
            "order_id": order_id,
            "rider_id": rider_profile.user_id,
            "payout": float(order.base_rate + order.distance_bonus),
            "base_rate": float(order.base_rate),
            "distance_bonus": float(order.distance_bonus),
            "eta_minutes": order.eta_minutes,
            "customer_message": customer_message,
            "vendor_message": vendor_message,
            "location_subscribe": locatin_subscribe
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/orders/reject/{order_id}/")
async def reject_order(
    order_id: str,
    reason: str = Form(...),
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    RIDER rejects an order
    """
    
    try:
        rider = await RiderProfile.get_or_none(user=user)
        if not rider:
            raise HTTPException(status_code=403, detail="Not a rider")
        
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != OrderStatus.PROCESSING:
            raise HTTPException(status_code=400, detail="Order not in processing state")
        
        # Update work day rejection count
        today = date.today()
        workday, _ = await WorkDay.get_or_create(
            rider=rider,
            date=today,
            defaults={"hours_worked": 0.0, "order_offer_count": 0}
        )
        workday.order_offer_count += 1
        await workday.save()
        
        logger.info(f"Order {order_id} rejected by rider {rider.id}. Reason: {reason}")
        
        return {"status": "rejected", "order_id": order_id, "reason": reason}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/orders/shipped/{order_id}/")
async def mark_order_shipped(
    order_id: str,
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    VENDOR marks order as shipped
    Flow: CONFIRMED -> SHIPPED
    """
    
    if not user.is_vendor:
        raise HTTPException(status_code=403, detail="Only vendors can mark shipped")
    
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Order must be confirmed first")
    
    order.status = OrderStatus.SHIPPED
    await order.save()
    
    notify_payload = {
        "type": "order_shipped",
        "order_id": order_id,
        "shipped_at": datetime.utcnow().isoformat()
    }
    
    await redis.publish("order_updates", json.dumps(notify_payload))
    
    try:
        await manager.send_notification("customers", str(order.user_id), "Order Shipped", "Your order has been picked up!")
        await send_notification(order.user_id, "Order Shipped", f"Your order is on the way!")
    except Exception as e:
        logger.warning(f"Shipment notification error: {str(e)}")
    
    return {"status": "shipped", "order_id": order_id}

@router.post("/orders/out-for-delivery/{order_id}/")
async def mark_order_out_for_delivery(
    order_id: str,
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    RIDER marks order as out for delivery
    Flow: SHIPPED -> OUT_FOR_DELIVERY
    """
    
    if not user.is_rider:
        raise HTTPException(status_code=403, detail="Only riders can update this")
    
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.SHIPPED:
        raise HTTPException(status_code=400, detail="Order not in shipped status")
    
    order.status = OrderStatus.OUT_FOR_DELIVERY
    await order.save()
    
    notify_payload = {
        "type": "order_out_for_delivery",
        "order_id": order_id,
        "out_for_delivery_at": datetime.utcnow().isoformat()
    }
    
    await redis.publish("order_updates", json.dumps(notify_payload))
    
    try:
        await manager.send_notification("customers", str(order.user_id), "Out for Delivery", "Your order is on its way!")
        await send_notification(order.user_id, "Out for Delivery", "Your order is arriving soon!")
    except Exception as e:
        logger.warning(f"Out for delivery notification error: {str(e)}")
    
    return {"status": "out_for_delivery", "order_id": order_id}

@router.post("/orders/delivered/{order_id}/")
async def mark_order_delivered(
    order_id: str,
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    RIDER marks order as delivered
    Flow: OUT_FOR_DELIVERY -> DELIVERED
    
    - Check if on-time
    - Update rider balance
    - Send notifications
    """
    
    if not user.is_rider:
        raise HTTPException(status_code=403, detail="Only riders can mark delivered")
    
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
    # now = datetime.utcnow()
    # if order.accepted_at and order.eta_minutes:
    #     eta_deadline = order.accepted_at + timedelta(minutes=order.eta_minutes)
    #     order.is_on_time = now <= eta_deadline
    # else:
    #     order.is_on_time = True
    now = datetime.now(timezone.utc)
    accepted_at = to_utc(order.accepted_at)      # ensure aware
    eta_deadline = accepted_at + timedelta(minutes=order.eta_minutes)

    order.is_on_time = now <= eta_deadline
    
    # Update order
    order.status = OrderStatus.DELIVERED
    order.completed_at = now
    await order.save()
    
    # Update rider balance
    rider = await RiderProfile.get_or_none(id=order.rider_id)
    if rider:
        payout = order.base_rate + order.distance_bonus
        rider.current_balance += payout
        await rider.save()
        
        logger.info(f"Rider {rider.id} balance updated: +₹{payout}")

    add_money_to_vendor_account(order.id)
    
    # Send notifications
    notify_payload = {
        "type": "order_delivered",
        "order_id": order_id,
        "delivered_at": now.isoformat(),
        "is_on_time": order.is_on_time,
        "payout": float(order.base_rate + order.distance_bonus)
    }
    
    await redis.publish("order_updates", json.dumps(notify_payload))
    
    try:
        await manager.send_notification("customers", str(order.user_id), "Order delivered", "Thank you for your order!")
        await manager.send_notification("vendors", str(vendor.usser_id), "Order Delivered", "Order {order_id} delivered successfully!")
        await send_notification(order.user_id, "Order Delivered", "Thank you for your order!")
    except Exception as e:
        logger.warning(f"Delivery notification error: {str(e)}")
    
    # End chat
    try:
        end_chat("riders", user.id, "customers", order.user_id)
        end_chat("riders", user.id, "vendors", vendor.user_id)
        subscribe_to_riders_location("unsubscribe", rider.user_id, order.user_id)
    except:
        pass
    
    return {
        "status": "delivered",
        "order_id": order_id,
        "is_on_time": order.is_on_time,
        "payout": float(order.base_rate + order.distance_bonus)
    }

@router.post("/orders/cancel/{order_id}/")
async def cancel_order(
    order_id: str,
    reason: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    redis = Depends(get_redis)
):
    """
    Cancel an order (can be customer or system)
    """
    
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
    order.reason = reason
    await order.save()
    
    notify_payload = {
        "type": "order_cancelled",
        "order_id": order_id,
        "cancelled_at": datetime.utcnow().isoformat(),
        "reason": reason
    }
    
    await redis.publish("order_updates", json.dumps(notify_payload))
    
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id), "notifications")
        await manager.send_to(notify_payload, "vendors", str(vendor.user_id), "notifications")
        await send_notification(order.user_id, "Order Cancelled", f"Reason: {reason or 'Not specified'}")
    except Exception as e:
        logger.warning(f"Cancellation notification error: {str(e)}")
    
    return {"status": "cancelled", "order_id": order_id}

@router.get("/orders/{order_id}/")
async def get_order_details(
    order_id: str,
    user: User = Depends(get_current_user),
):
    """Get order details"""
    
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    rider = await RiderProfile.get_or_none(id=order.rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    order_item = await OrderItem.get_or_none(order=order)
    if not order_item:
        raise HTTPException(status_code=404, detail="Order item not found")
    
    item = await Item.get_or_none(id=order_item.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    vendor = await VendorProfile.get_or_none(id=item.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    
    return {
        "id": order.id,
        "status": order.status,
        "rider_id": rider.user_id,
        "vendor_id": vendor.user_id,
        "customer_id": order.user_id,
        "base_rate": float(order.base_rate),
        "distance_bonus": float(order.distance_bonus),
        "total_payout": float((order.base_rate or 0) + (order.distance_bonus or 0)),
        "eta_minutes": order.eta_minutes,
        "is_on_time": order.is_on_time,
        "is_combined": order.is_combined,
        "combined_pickups": order.combined_pickups,
        "delivery_type": order.delivery_type,
        "accepted_at": order.accepted_at,
        "completed_at": order.completed_at
    }



def to_utc(dt: datetime) -> datetime:
    if dt is None:
        return None
    # if naive, assume it's UTC (adjust if your DB stores local tz)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


