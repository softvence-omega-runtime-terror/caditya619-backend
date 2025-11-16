from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time, timedelta
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, OrderOffer, RiderCurrentLocation
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from tortoise.contrib.pydantic import pydantic_model_creator
from applications.customer.models import Order, OrderStatus
import uuid
from app.utils.geo import haversine, bbox_for_radius
import json
from app.utils.websocket_manager import manager
from tortoise.transactions import in_transaction
#from helper_functions import start_chat, end_chat
from .helper_functions import start_chat, end_chat


# from datetime import time as _time
# from app.utils.websocket_manager import manager
# import json
# from app.redis import redis_client
from starlette.websockets import WebSocketDisconnect, WebSocket
import asyncio
# from app.utils.map_distance_ETA import haversine, estimate_eta
# from fastapi.responses import HTMLResponse
from app.redis import get_redis




from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider Orders'])



OFFER_TIMEOUT_SECONDS = 60  # riders must accept within this many seconds
GEO_REDIS_KEY = "riders_geo"  # if you use Redis GEO

@router.post("/orders/{order_id}/", status_code=201)
async def create_order(
    order_id: str,
    customer_lat: float,
    customer_lng: float,
    vendor_lat: float,
    vendor_lng: float,
    top_n: int = 20,
    radius_km: float = 5.0,
    current_user = Depends(get_current_user),
    redis = Depends(get_redis)
):
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="User type is not vendor")

    # 0. Basic checks
    if top_n <= 0 or radius_km <= 0:
        raise HTTPException(status_code=400, detail="Invalid parameters")


    order = await Order.get_or_none(id=order_id)
    print(f"order is {order.id, order.status}")

    order.status = OrderStatus.PENDING  
    await order.save()

    print(f"order is {order.id, order.status}")

    # 2. Try Redis GEO to find candidate rider ids (fast path)
    candidate_rider_ids: List[int] = []
    try:
        geo_res = await redis.execute_command(
            "GEOSEARCH", GEO_REDIS_KEY,
            "FROMLONLAT", vendor_lng, vendor_lat,
            "BYRADIUS", radius_km, "km",
            "ASC",
            "COUNT", top_n * 3
        )
        # geo_res are bytes in some clients; decode to ints if needed
        candidate_rider_ids = [int(x) for x in geo_res]
    except Exception:
        # Redis GEO not configured or failed — fallback to DB
        candidate_rider_ids = []

    candidates = []
    if candidate_rider_ids:
        print("from 1")
        # fetch rider profiles and current_location
        riders = await RiderProfile.filter(id__in=candidate_rider_ids, is_available=True).prefetch_related("current_location").all()
        # order by the geo result order
        id_to_idx = {rid: i for i, rid in enumerate(candidate_rider_ids)}
        riders.sort(key=lambda r: id_to_idx.get(r.id, 9999))
        # filter by distance precisely
        for r in riders:
            current_location = await RiderCurrentLocation.filter(rider_profile = r).first()
            if not hasattr(r, "current_location") or current_location is None:
                continue
            dist = haversine(vendor_lat, vendor_lng, current_location.latitude, current_location.longitude)
            if dist <= radius_km:
                candidates.append((r, dist))
    else:
        print("from 2")
        # DB fallback: bbox then haversine
        lat_min, lat_max, lng_min, lng_max = bbox_for_radius(vendor_lat, vendor_lng, radius_km)
        print(f'latmin {lat_min}, latmax{lat_max}, lngmin{lng_min}, lngmax{lng_max}')
        # join RiderProfile + RiderCurrentLocation - simplest: prefetch current_location
        riders = await RiderProfile.filter(
            is_available=True
        ).all()

        print(riders)

        for r in riders:

            # loc = getattr(r, "current_location", None)
            loc = await RiderCurrentLocation.filter(rider_profile=r).first()
            
            if not loc:
                print("loc ", loc.latitude)
                continue
            if not (lat_min <= loc.latitude <= lat_max and lng_min <= loc.longitude <= lng_max):
                print("min 2")
                continue
            dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
            if dist <= radius_km:
                candidates.append((r, dist))

    # sort by distance and take top_n
    candidates.sort(key=lambda x: x[1])
    chosen = [c[0] for c in candidates[:top_n]]

    if not chosen:
        # fallback: expand radius OR fallback to zone-based assignment (not implemented here)
        #await order.delete()
        raise HTTPException(status_code=400, detail="No riders available")

    # 3. Create OrderOffer rows inside transaction
    expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
    async with in_transaction() as conn:
        offers = []
        for r in chosen:
            offer = await OrderOffer.create(
                order=order,
                rider=r,
                customer_lat=customer_lat,
                customer_lng=customer_lng,
                vendor_lat=vendor_lat,
                vendor_lng=vendor_lng,
                offered_at=datetime.utcnow(),
                status="offered",
                expires_at=expires_at,
            )
            offers.append(offer)

        #order.offered_to_count = len(offers)
        await order.save(using_db=conn)

    # 4. Notify riders: publish Redis pubsub (cross-instance) + local websocket via manager
    payload = {
        "type": "order_offer",
        "order_id": order.id,
        "customer_id": current_user.id,
        "vendor_lat": vendor_lat,
        "vendor_lng": vendor_lng,
        "customer_lat": customer_lat,
        "customer_lng": customer_lng,
        "expires_at": expires_at.isoformat()
    }
    for offer in offers:
        # publish per-offer data with rider id
        per_payload = {**payload, "rider_id": offer.rider_id}
        await redis.publish("order_offers", json.dumps(per_payload))
        # try to send to local socket if connected
        await manager.send_to(per_payload, "riders", str(offer.rider_id))

    return {"order_id": order.id, "offered_to": [o.rider_id for o in offers]}






@router.post("/orders/{order_id}/accept/")
async def accept_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    print("hello")
    claim_key = f"order_claim:{order_id}"
    # attempt to claim: atomic set NX
    claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)  # 30s to finalize
    if not claimed:
        # someone else claimed
        raise HTTPException(status_code=400, detail="Order already claimed")
    
    rider_profile = await RiderProfile.filter(user= user).first()

    print(rider_profile)

    # validate offer exists
    offer = await OrderOffer.get_or_none(order__id=order_id, rider=rider_profile, status="offered").first()
    if not offer:
        # release lock (optional)
        await redis.delete(claim_key)
        raise HTTPException(status_code=403, detail="Order not offered to this rider or already responded")

    # finalize acceptance in DB
    async with in_transaction() as conn:
        order = await Order.get(id=order_id).using_db(conn)
        # double-check order state
        if offer.status != "offered":
            # another server might have processed
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available")

        # assign rider and change status
        order.status = OrderStatus.CONFIRMED
        # ensure your Order model has a rider foreign key; if not, set metadata
        order.metadata = order.metadata or {}
        order.metadata["rider_id"] = user.id
        order.accepted_at = datetime.utcnow()
        await order.save(using_db=conn)

        # mark offers
        await OrderOffer.filter(order=order).exclude(rider=rider_profile).update(status="rejected", responded_at=datetime.utcnow())
        await OrderOffer.filter(order=order, rider=rider_profile).update(status="accepted", responded_at=datetime.utcnow())

    # notify customer & vendor
    notify_payload = {
        "type": "order_accepted",
        "order_id": order_id,
        "rider_id": user.id,
        "accepted_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))

    # local websocket notify customer and vendor if connected
    # ensure order has customer_id and vendor_id available
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except Exception:
        pass

    massage = start_chat("riders", user.id, "customers", order.user_id)

    # You may choose to keep the claim key for longer to prevent reassign, or delete it now
    await redis.delete(claim_key)
    return {"status": "accepted", "order_id": order_id, "rider_id": user.id, "massage": massage}







@router.post("/orders/{order_id}/reject")
async def reject_order(order_id: str, rider_id: int, reason: str = None):
    offer = await OrderOffer.get_or_none(order_id=order_id, rider_id=rider_id, status="offered")
    if not offer:
        raise HTTPException(status_code=400, detail="No active offer to reject")
    offer.status = "rejected"
    offer.reason = reason
    offer.responded_at = datetime.utcnow()
    await offer.save()
    # optionally increment rider rejection counters
    rider = await RiderProfile.get(id=rider_id)
    rider.orders_rejected = (getattr(rider, "orders_rejected", 0) + 1)
    await rider.save()
    return {"status": "rejected"}





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
    
    # ADD CUSTOMER TO RIDER'S TRACKING LIST
    if client_type == "customer":
        manager.add_tracking(str(offer.rider_id), user_id)

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




@router.post("/orders/{order_id}/complete")
async def complete_order(order_id: int, rider_id: int):
    order = await Order.get(id=order_id)
    if order.rider_id != rider_id:
        raise HTTPException(403, "Not your order")

    order.status = "delivered"
    await order.save()

    # NOTIFY CUSTOMER
    await manager.send_to({
        "type": "order_delivered",
        "order_id": order_id,
        "message": "Your order has been delivered!"
    }, "customers", str(order.customer_id))

    # CRITICAL: Remove customer from rider's tracking list
    manager.rider_to_customers[str(rider_id)].discard(str(order.customer_id))
    manager.customer_to_rider.pop(str(order.customer_id), None)

    return {"status": "delivered"}








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



