from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time, timedelta
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, OrderOffer, RiderCurrentLocation, WorkDay, RiderFeesAndBonuses
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from tortoise.contrib.pydantic import pydantic_model_creator
from applications.customer.models import Order, OrderStatus, OrderItem
from applications.items.models import Item
from applications.user.vendor import VendorProfile
from applications.user.customer import CustomerProfile
import uuid
from app.utils.geo import haversine, bbox_for_radius, estimate_eta
import json
from app.utils.websocket_manager import manager
from tortoise.transactions import in_transaction
#from helper_functions import start_chat, end_chat
from .helper_functions import start_chat, end_chat
from starlette.websockets import WebSocketDisconnect, WebSocket
import asyncio
# from app.utils.map_distance_ETA import haversine, estimate_eta
# from fastapi.responses import HTMLResponse
from app.redis import get_redis
#from fastapi.background import BackgroundTasks
import logging
from datetime import timezone
from .notifications import send_notification





from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider Orders'])



OFFER_TIMEOUT_SECONDS = 1200
GEO_REDIS_KEY = "riders_geo"
INITIAL_RADIUS_KM = 5.0
RADIUS_STEP_KM = 5.0
MAX_RADIUS_KM = 20.0


# Add expires_at to OrderOffer if not
# expires_at = fields.DatetimeField(null=True)

# Add to WorkDay if needed: orders_accepted = fields.IntField(default=0)



logger = logging.getLogger(__name__)

async def notify_rider(rider_id: int,order: "Order"):
    payload = {
        "type": "order_offer",
        "order_id": order.id
    }
    rider = await RiderProfile.get_or_none(id=rider_id)
    redis = get_redis()  # Assume this works; in prod, consider pooling or injecting
    await redis.publish("order_offers", json.dumps(payload))
    print(f"user id is {rider.user_id}")
    await manager.send_to(payload, "riders", str(rider.user_id))
    try:
        await send_notification(rider.user_id, "New Order Offer", f"You have a new order offer: {order.id}")
    except Exception as e:
        logger.error(f"Failed to send notification to rider {rider_id}: {str(e)}")


async def offer_sequential(order_id: str, prepire_time: int):
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            logger.error(f"Order {order_id} not found for sequential offering")
            return
        candidates = order.metadata.get("candidate_riders", [])
        if candidates:
            order.status = OrderStatus.PROCESSING
            order.prepire_time = prepire_time
            await order.save()
            
        for i, rider_id in enumerate(candidates):
            rider = await RiderProfile.get_or_none(id=rider_id)
            if not rider:
                continue
            if order.status != OrderStatus.PROCESSING:
                break
            await notify_rider(rider_id, order)
            today = date.today()
            workday, _ = await WorkDay.get_or_create(rider=rider, date=today, defaults={"hours_worked": 0.0, "orders_accepted": 0})
            workday.order_offer_count += 1
            await workday.save()
            #await asyncio.sleep(OFFER_TIMEOUT_SECONDS)
            if order.status != OrderStatus.PROCESSING:
                break
    except Exception as e:
        logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")








@router.post("/order-offers/{order_id}/", status_code=201)
async def create_order(
    order_id: str,
    background_tasks: BackgroundTasks,
    prepire_time: int = Form(),
    top_n: int = 20,
    current_user = Depends(get_current_user),
    redis = Depends(get_redis)
):
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="User type is not vendor")
    if top_n <= 0:
        raise HTTPException(status_code=400, detail="Invalid parameters")
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    order_item = await OrderItem.get_or_none(order=order)
    if not order_item:
        raise HTTPException(404, "Order item not found")
    
    item = await Item.get_or_none(id=order_item.item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    vendor = await VendorProfile.get_or_none(id=item.vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    # customer = await CustomerProfile.get_or_none(id=order.user_id)
    # if not customer:
    #     raise HTTPException(404, "Customer not found")

    # Add vendor_lat etc to order if needed
    order.status = OrderStatus.PENDING
    await order.save()
    print(f"order current status is {order.status}")
    candidates = []
    radius = INITIAL_RADIUS_KM
    existing_ids = set()
    while len(candidates) < top_n and radius <= MAX_RADIUS_KM:
        candidate_rider_ids = []
        try:
            geo_res = await redis.execute_command(
                "GEOSEARCH", GEO_REDIS_KEY,
                "FROMLONLAT", vendor.latitude, vendor.longitude,
                "BYRADIUS", radius, "km",
                "ASC",
                "COUNT", top_n * 3
            )
            candidate_rider_ids = [int(x) for x in geo_res if int(x) not in existing_ids]
        except Exception:
            pass
        temp_candidates = []
        if candidate_rider_ids:
            riders = await RiderProfile.filter(id__in=candidate_rider_ids, is_available=True).prefetch_related("current_location").all()
            id_to_idx = {rid: i for i, rid in enumerate(candidate_rider_ids)}
            riders.sort(key=lambda r: id_to_idx.get(r.id, 9999))
            for r in riders:
                loc = r.current_location
                if not loc:
                    continue
                dist = haversine(vendor.latitude, vendor.longitude, loc.latitude, loc.longitude)
                if dist <= radius:
                    temp_candidates.append((r, dist))
                    existing_ids.add(r.id)
        else:
            lat_min, lat_max, lng_min, lng_max = bbox_for_radius(vendor.latitude, vendor.longitude, radius)
            riders = await RiderProfile.filter(is_available=True).prefetch_related("current_location").all()
            for r in riders:
                if r.id in existing_ids:
                    continue
                loc = r.current_location
                if not loc:
                    continue
                if not (lat_min <= loc.latitude <= lat_max and lng_min <= loc.longitude <= lng_max):
                    continue
                dist = haversine(vendor.latitude, vendor.longitude, loc.latitude, loc.longitude)
                if dist <= radius:
                    temp_candidates.append((r, dist))
                    existing_ids.add(r.id)
        candidates.extend(temp_candidates)
        candidates.sort(key=lambda x: x[1])
        candidates = candidates[:top_n]
        radius += RADIUS_STEP_KM
    if not candidates:
        raise HTTPException(status_code=400, detail="No riders available")
    chosen = [c[0] for c in candidates]
    order.metadata = order.metadata or {}
    order.metadata["candidate_riders"] = [r.id for r in chosen]
    await order.save()
    # For background async
    background_tasks.add_task(offer_sequential, order_id, prepire_time)  # Assume setup for async background
    return {"order_id": order.id, "potential_offers": len(chosen)}






@router.post("/orders/accept/{order_id}/")
async def accept_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    rider_profile = await RiderProfile.filter(user=user).first()
    if not rider_profile:
        raise HTTPException(403, "Not a rider")
    claim_key = f"order_claim:{order_id}"
    claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)
    if not claimed:
        raise HTTPException(status_code=400, detail="Order already claimed")
    order = await Order.get(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    now = datetime.now(timezone.utc)
    if order.expires_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
        print(f"expires at is {order.expires_at} and now is {now}")
        await redis.delete(claim_key)
        raise HTTPException(400, "Offer expired")
    async with in_transaction() as conn:
        # order = await Order.get(id=order_id).using_db(conn)
        if order.status != OrderStatus.PROCESSING:
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available")
        order.status = OrderStatus.CONFIRMED
        order.rider = rider_profile

        customer = await CustomerProfile.get_or_none(id=order.user_id)
        if not customer:
            raise HTTPException(404, "Customer not found")
        

        loc = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
        if not loc:
            raise HTTPException(400, "Rider location not found")
        order_item = await OrderItem.get_or_none(order=order)
        if not order_item:
            raise HTTPException(404, "Order item not found")
        
        item = await Item.get_or_none(id=order_item.item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        vendor = await VendorProfile.get_or_none(id=item.vendor_id)
        if not vendor:
            raise HTTPException(404, "Vendor not found")
        vendor_lat = vendor.latitude
        vendor_lng = vendor.longitude
        dist1 = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
        dist2 = haversine(loc.latitude, loc.longitude, customer.customer_lat, customer.customer_lng)
        feesandbonus = await RiderFeesAndBonuses.get(id = 1)
        if not feesandbonus:
            raise HTTPException(status_code=500, detail="Rider fees and bonuses not configured")
        pickup_time = datetime.utcnow() + timedelta(minutes=10)  # estimate
        eta_minutes = int(estimate_eta(dist1).total_seconds() / 60) + int(estimate_eta(dist2).total_seconds() / 60) + order.prepire_time
        base_rate = feesandbonus.rider_delivery_fee or 44.00
        distance_bonus = max((dist1+dist2) - 3, 0) * (feesandbonus.distance_bonus_per_km or 1.0)
        expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
        
        order.pickup_distance_km = dist1
        order.pickup_time = pickup_time
        order.eta_minutes = eta_minutes
        order.base_rate = base_rate
        order.distance_bonus = distance_bonus
        order.offered_at = datetime.utcnow()
        order.expires_at = expires_at
        order.metadata = order.metadata or {}
        order.metadata["rider_id"] = rider_profile.id
        # await order.save(using_db=conn)
        order.accepted_at = datetime.utcnow()
        await order.save(using_db=conn)
        # Reject others if any
        await OrderOffer.filter(order=order).exclude(rider=rider_profile).update(status="rejected", responded_at=datetime.utcnow())
   
    notify_payload = {
        "type": "order_accepted",
        "order_id": order_id,
        "rider_id": rider_profile.id,
        "accepted_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
        await manager.send_to(notify_payload, "vendors", str(vendor.user_id))
    except:
        pass
    try:
        await send_notification(order.user_id, "Order Accepted", f"Your order {order.id} has been accepted by a {rider_profile.user.name}.")
        await send_notification(vendor.user_id, "Order Accepted", f"Order {order.id} has been accepted by rider {rider_profile.user.name}.")
    except Exception as e:
        logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")
    customer_message = start_chat("riders", user.id, "customers", order.user_id)
    vendor_message = start_chat("riders", user.id, "vendors", vendor.user_id)
    await redis.delete(claim_key)
    return {"status": "accepted", "order_id": order_id, "rider_id": rider_profile.id, "customer_message": customer_message, "vendor_message": vendor_message}






@router.post("/orders/shipped/{order_id}/")
async def mark_order_shipped(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):

    if not user.is_vendor:
        raise HTTPException(403, "User is not a vendor")
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(400, "Order not in confirmed status")
    order.status = OrderStatus.SHIPPED
    await order.save()
    offer = await OrderOffer.filter(order_id=order_id).first()
    notify_payload = {
        "type": "order_shipped",
        "order_id": order_id,
        "rider_id": offer.rider_id,
        "shipped_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass

    try:
        await send_notification(order.user_id, "Order Shipped", f"Your order {order.id} has been shipped and is on its way!")
    except Exception as e:
        logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")

    return {"status": "shipped", "order_id": order_id, "rider_id": offer.rider_id}






@router.post("/orders/out-for-delivery/{order_id}/")
async def mark_order_out_for_delivery(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    if not user.is_rider:
        raise HTTPException(403, "User is not a valid rider")
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != OrderStatus.SHIPPED:
        raise HTTPException(400, "Order not in shipped status")
    order.status = OrderStatus.OUT_FOR_DELIVERY
    await order.save()
    notify_payload = {
        "type": "order_out_for_delivery",
        "order_id": order_id,
        "out_for_delivery_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass
    try:
        await send_notification(order.user_id, "Order Out for Delivery", f"Your order {order.id} is out for delivery!")
    except Exception as e:
        logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")

    return {"status": "out_for_delivery", "order_id": order_id, "rider_id": order.rider_id}




@router.post("/orders/delivered/{order_id}/")
async def mark_order_delivered(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    if not user.is_rider:
        raise HTTPException(403, "User is not a valid rider")
    
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != OrderStatus.OUT_FOR_DELIVERY:
        raise HTTPException(400, "Order not in out for delivery status")
    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.utcnow()
    await order.save()
    notify_payload = {
        "type": "order_delivered",
        "order_id": order_id,
        "delivered_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass
    try:
        await send_notification(order.user_id, "Order Delivered", f"Your order {order.id} has been delivered successfully!")
    except Exception as e:
        logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")
    return {"status": "delivered", "order_id": order_id, "rider_id": order.rider_id}




@router.post("/orders/cancel/{order_id}/")
async def cancel_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
        raise HTTPException(400, "Order cannot be cancelled")
    order.status = OrderStatus.CANCELLED
    await order.save()
    notify_payload = {
        "type": "order_cancelled",
        "order_id": order_id,
        "cancelled_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass
    try:
        await send_notification(order.user_id, "Order Cancelled", f"Your order {order.id} has been cancelled.")
    except Exception as e:
        logger.error(f"Failed to send notification to customer {order.user_id}: {str(e)}")
    return {"status": "cancelled", "order_id": order_id}






#**********************************************************************************************
#           WEBSOCKET ENDPOINTS
#**********************************************************************************************



@router.websocket("/ws/rider/location/{rider_id}")
async def rider_location_ws(
    websocket: WebSocket,
    rider_id: str,
    redis = Depends(get_redis)
):
    await manager.connect(websocket, "riders", rider_id)
    try:
        user = await User.get(id=int(rider_id))
        rider = await RiderProfile.get(user=user)
        loc = await RiderCurrentLocation.get(rider_profile= rider)
        while True:
            data = await websocket.receive_json()
            lat = data.get("lat")
            lng = data.get("lng")

            # Update DB
            loc.latitude = lat
            loc.longitude = lng
            #loc.is_active = True
            await loc.save()

            # Prepare message
            location_msg = {
                "type": "location_update",
                "rider_id": rider_id,
                "lat": lat,
                "lng": lng,
                "timestamp": datetime.utcnow().isoformat()
            }

            # SEND ONLY TO CUSTOMERS TRACKING THIS RIDER
            await manager.send_location_to_tracking_customers(rider_id, location_msg)

            # Optional: Still publish to Redis for analytics
            await redis.publish("rider_locations", json.dumps({
                "rider_id": rider_id,
                "lat": lat,
                "lng": lng
            }))

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        manager.disconnect("riders", rider_id)
        # rider.is_active = False
        # await rider.save()



@router.websocket("/ws/track/{order_id}/{client_type}/{user_id}")
async def track_order(
    websocket: WebSocket,
    order_id: str,
    client_type: str,
    user_id: int
):
    if client_type not in ["customer", "vendor"]:
        await websocket.close(code=1008)
        return

    order = await Order.get(id=order_id)
    offer = await OrderOffer.get(order=order).first()
    if not offer.rider:
        await websocket.close(code=4000, reason="No rider assigned")
        return

    if client_type == "customer" and order.user_id != int(user_id):
        await websocket.close(code=4003, reason="Unauthorized")
        return

    # CONNECT & ADD TO TRACKING
    await manager.connect(websocket, "customers" if client_type == "customer" else "vendors", user_id)

    rider = await RiderProfile.get(id=offer.rider_id)
    if not rider:
        await websocket.close(code=4001, reason="Rider not found")
        return
    
    # ADD CUSTOMER TO RIDER'S TRACKING LIST
    if client_type == "customer":
        manager.add_tracking(str(rider.user_id), user_id)

    try:
        # Send initial state
        await manager.send_to({
            "type": "order_state",
            "order_id": order_id,
            "status": order.status,
            "rider_id": offer.rider_id,
            #"eta_pickup": order.estimated_pickup.isoformat() if order.estimated_pickup else None
        }, client_type, user_id)

        while True:
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect("customers" if client_type == "customer" else "vendors", user_id)








@router.websocket("/ws/{client_type}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_type: str,
    user_id: str,
    redis = Depends(get_redis)
):
    if client_type not in {"riders", "customers", "vendors"}:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, client_type, user_id)

    try:
        while True:
            raw = await websocket.receive_text()
            raw = raw.strip()
            if not raw:
                continue

            try:
                msg = json.loads(raw)
                text = msg.get("text", "")
                to_type = msg.get("to_type")
                to_id = msg.get("to_id")
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            # REQUIRED: Must specify who to send to
            if not text or not to_type or not to_id:
                await websocket.send_json({
                    "error": "Missing text/to_type/to_id",
                    "example": {"text": "Hi", "to_type": "customers", "to_id": 8}
                })
                continue

            to_id_str = str(to_id)

            # VALIDATE: You must have an active chat with this person
            if not manager.is_chatting_with(client_type, user_id, to_type, to_id_str):
                await websocket.send_json({"error": "No active chat with this user"})
                continue

            # BUILD MESSAGE
            payload = {
                "from_type": client_type,
                "from_id": user_id,
                "from_name": getattr(websocket.state, "username", user_id),  # optional
                "text": text,
                "timestamp": datetime.utcnow().isoformat()
            }

            # SEND ONLY TO THIS ONE PERSON
            channel = f"msg:{to_type}:{to_id_str}"
            await redis.publish(channel, json.dumps(payload))
            await manager.send_to(payload, to_type, to_id_str)

            # Optional: Confirm sent
            await websocket.send_json({"status": "sent", "to": f"{to_type}:{to_id_str}"})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(client_type, user_id)








@router.websocket("/ws/")
async def ws_endpoint(ws: WebSocket):
    client_type = ws.query_params.get("client_type")  # "riders" / "customers" / "vendors"
    user_id = ws.query_params.get("user_id")          # e.g. "123"
    if not client_type or not user_id:
        await ws.close(code=4001)
        return

    await manager.connect(ws, client_type, user_id)
    try:
        while True:
            await ws.receive_text()  # keep connection alive; ignore inbound payloads for test
    except WebSocketDisconnect:
        manager.disconnect(client_type, user_id)

