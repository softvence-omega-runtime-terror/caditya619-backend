from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time, timedelta
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, OrderOffer, RiderCurrentLocation, WorkDay
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from tortoise.contrib.pydantic import pydantic_model_creator
from applications.customer.models import Order, OrderStatus
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

async def notify_rider(rider_id: int, offer: OrderOffer, order: "Order"):
    payload = {
        "type": "order_offer",
        "order_id": order.id,
        "offer_id": offer.id,
        "vendor_lat": offer.vendor_lat,
        "vendor_lng": offer.vendor_lng,
        "customer_lat": offer.customer_lat,
        "customer_lng": offer.customer_lng,
        "pickup_distance_km": offer.pickup_distance_km,
        "pickup_time": offer.pickup_time.isoformat(),
        "eta_minutes": offer.eta_minutes,
        "base_rate": float(offer.base_rate),
        "distance_bonus": float(offer.distance_bonus),
        "expires_at": offer.expires_at.isoformat()
    }
    redis = get_redis()  # Assume this works; in prod, consider pooling or injecting
    await redis.publish("order_offers", json.dumps(payload))
    await manager.send_to(payload, "riders", str(rider_id))

async def offer_sequential(order_id: str, customer_lat: float, customer_lng: float, vendor_lat: float, vendor_lng: float):
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            logger.error(f"Order {order_id} not found for sequential offering")
            return
        candidates = order.metadata.get("candidate_riders", [])
        for i, rider_id in enumerate(candidates):
            rider = await RiderProfile.get_or_none(id=rider_id)
            if not rider:
                continue
            loc = await RiderCurrentLocation.get_or_none(rider_profile=rider)
            if not loc:
                continue
            dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
            pickup_time = datetime.utcnow() + timedelta(minutes=10)  # estimate
            eta_minutes = int(estimate_eta(dist).total_seconds() / 60)
            base_rate = 44.00
            distance_bonus = max(dist - 3, 0) * 1.0
            expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
            offer = await OrderOffer.create(
                order=order,
                rider=rider,
                customer_lat=customer_lat,
                customer_lng=customer_lng,
                vendor_lat=vendor_lat,
                vendor_lng=vendor_lng,
                status="offered",
                pickup_distance_km=dist,
                pickup_time=pickup_time,
                eta_minutes=eta_minutes,
                base_rate=base_rate,
                distance_bonus=distance_bonus,
                offered_at=datetime.utcnow(),
                expires_at=expires_at
            )
            await notify_rider(rider_id, offer, order)
            rider_profile = await RiderProfile.get(id=rider_id)
            if not rider_profile:
                continue
            today = date.today()
            workday, _ = await WorkDay.get_or_create(rider=rider_profile, date=today, defaults={"hours_worked": 0.0, "orders_accepted": 0})
            workday.order_offer_count += 1
            await workday.save()
            await asyncio.sleep(OFFER_TIMEOUT_SECONDS)
            offer = await OrderOffer.get(id=offer.id)
            if offer.status == "offered":
                offer.status = "timeout"
                await offer.save()
            order = await Order.get(id=order_id)
            if order.status != OrderStatus.PENDING:
                break
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            await order.save()
            logger.info(f"Order {order_id} cancelled due to no acceptance")
    except Exception as e:
        logger.error(f"Error in sequential offering for order {order_id}: {str(e)}")








@router.post("/order-offers/{order_id}/", status_code=201)
async def create_order(
    order_id: str,
    customer_lat: float,
    customer_lng: float,
    vendor_lat: float,
    vendor_lng: float,
    background_tasks: BackgroundTasks,
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
    # Add vendor_lat etc to order if needed
    order.vendor_lat = vendor_lat  # assume fields
    order.vendor_lng = vendor_lng
    order.customer_lat = customer_lat
    order.customer_lng = customer_lng
    order.status = OrderStatus.PENDING
    await order.save()
    candidates = []
    radius = INITIAL_RADIUS_KM
    existing_ids = set()
    while len(candidates) < top_n and radius <= MAX_RADIUS_KM:
        candidate_rider_ids = []
        try:
            geo_res = await redis.execute_command(
                "GEOSEARCH", GEO_REDIS_KEY,
                "FROMLONLAT", vendor_lng, vendor_lat,
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
                dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
                if dist <= radius:
                    temp_candidates.append((r, dist))
                    existing_ids.add(r.id)
        else:
            lat_min, lat_max, lng_min, lng_max = bbox_for_radius(vendor_lat, vendor_lng, radius)
            riders = await RiderProfile.filter(is_available=True).prefetch_related("current_location").all()
            for r in riders:
                if r.id in existing_ids:
                    continue
                loc = r.current_location
                if not loc:
                    continue
                if not (lat_min <= loc.latitude <= lat_max and lng_min <= loc.longitude <= lng_max):
                    continue
                dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
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
    background_tasks.add_task(offer_sequential, order_id, customer_lat, customer_lng, vendor_lat, vendor_lng)
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
    offer = await OrderOffer.filter(rider=rider_profile, status="offered").first()
    if not offer:
        await redis.delete(claim_key)
        raise HTTPException(status_code=403, detail="Order not offered to this rider or already responded")
    now = datetime.now(timezone.utc)
    if offer.expires_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
        print(f"expires at is {offer.expires_at} and now is {now}")
        await redis.delete(claim_key)
        raise HTTPException(400, "Offer expired")
    async with in_transaction() as conn:
        order = await Order.get(id=order_id).using_db(conn)
        if offer.status != "offered":
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available")
        order.status = OrderStatus.CONFIRMED
        order.metadata = order.metadata or {}
        order.metadata["rider_id"] = rider_profile.id
        order.accepted_at = datetime.utcnow()
        await order.save(using_db=conn)
        offer.status = "accepted"
        offer.responded_at = datetime.utcnow()
        offer.accepted_at = datetime.utcnow()
        await offer.save(using_db=conn)
        # Reject others if any
        await OrderOffer.filter(order=order).exclude(rider=rider_profile).update(status="rejected", responded_at=datetime.utcnow())
    # Update WorkDay
    # today = date.today()
    # workday, _ = await WorkDay.get_or_create(rider=rider_profile, date=today, defaults={"hours_worked": 0.0, "orders_accepted": 0})
    # workday.orders_accepted += 1
    # await workday.save()
    # Notify
    notify_payload = {
        "type": "order_accepted",
        "order_id": order_id,
        "rider_id": rider_profile.id,
        "accepted_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass
    message = start_chat("riders", user.id, "customers", order.user_id)
    await redis.delete(claim_key)
    return {"status": "accepted", "order_id": order_id, "rider_id": rider_profile.id, "message": message}








""" async def notify_rider(rider_id: int, offer: OrderOffer, order: "Order"):
    payload = {
        "type": "order_offer",
        "order_id": order.id,
        "offer_id": offer.id,
        "vendor_lat": offer.vendor_lat,
        "vendor_lng": offer.vendor_lng,
        "customer_lat": offer.customer_lat,
        "customer_lng": offer.customer_lng,
        "pickup_distance_km": offer.pickup_distance_km,
        "pickup_time": offer.pickup_time.isoformat(),
        "eta_minutes": offer.eta_minutes,
        "base_rate": float(offer.base_rate),
        "distance_bonus": float(offer.distance_bonus),
        "expires_at": offer.expires_at.isoformat()
    }
    redis = get_redis()  # Assume get in func or inject
    await redis.publish("order_offers", json.dumps(payload))
    await manager.send_to(payload, "riders", str(rider_id))

async def offer_sequential(order_id: str, customer_lat: float, customer_lng: float, vendor_lat: float, vendor_lng: float):
    order = await Order.get_or_none(id=order_id)
    if not order:
        return
    candidates = order.metadata.get("candidate_riders", [])
    for i, rider_id in enumerate(candidates):
        rider = await RiderProfile.get_or_none(id=rider_id)
        if not rider:
            continue
        loc = await RiderCurrentLocation.get_or_none(rider_profile=rider)
        if not loc:
            continue
        dist = haversine(order.vendor_lat, order.vendor_lng, loc.latitude, loc.longitude)  # Assume order has vendor_lat etc, or pass
        pickup_time = datetime.utcnow() + timedelta(minutes=10)  # estimate
        eta_minutes = int(estimate_eta(dist).total_seconds() / 60)
        base_rate = 44.00
        distance_bonus = max(dist - 3, 0) * 1.0
        expires_at = datetime.utcnow() + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
        offer = await OrderOffer.create(
            order=order,
            rider=rider,
            customer_lat=customer_lat,  # assume from params or order
            customer_lng=customer_lng,
            vendor_lat=vendor_lat,
            vendor_lng=vendor_lng,
            status="offered",
            pickup_distance_km=dist,
            pickup_time=pickup_time,
            eta_minutes=eta_minutes,
            base_rate=base_rate,
            distance_bonus=distance_bonus,
            offered_at=datetime.utcnow(),
            expires_at=expires_at
        )
        await notify_rider(rider_id, offer, order)
        await asyncio.sleep(OFFER_TIMEOUT_SECONDS)
        offer = await OrderOffer.get(id=offer.id)
        if offer.status == "offered":
            offer.status = "timeout"
            await offer.save()
        order = await Order.get(id=order_id)
        if order.status != OrderStatus.PENDING:
            break
    if order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CANCELLED
        await order.save()

@router.post("/orders/{order_id}/", status_code=201)
async def create_order(
    order_id: str,
    customer_lat: float,
    customer_lng: float,
    vendor_lat: float,
    vendor_lng: float,
    top_n: int = 20,
    background_tasks: BackgroundTasks = Depends(),
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
    # Add vendor_lat etc to order if needed
    order.vendor_lat = vendor_lat  # assume fields
    order.vendor_lng = vendor_lng
    order.customer_lat = customer_lat
    order.customer_lng = customer_lng
    order.status = OrderStatus.PENDING
    await order.save()
    candidates = []
    radius = INITIAL_RADIUS_KM
    existing_ids = set()
    while len(candidates) < top_n and radius <= MAX_RADIUS_KM:
        candidate_rider_ids = []
        try:
            geo_res = await redis.execute_command(
                "GEOSEARCH", GEO_REDIS_KEY,
                "FROMLONLAT", vendor_lng, vendor_lat,
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
                dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
                if dist <= radius:
                    temp_candidates.append((r, dist))
                    existing_ids.add(r.id)
        else:
            lat_min, lat_max, lng_min, lng_max = bbox_for_radius(vendor_lat, vendor_lng, radius)
            riders = await RiderProfile.filter(is_available=True).prefetch_related("current_location").all()
            for r in riders:
                if r.id in existing_ids:
                    continue
                loc = r.current_location
                if not loc:
                    continue
                if not (lat_min <= loc.latitude <= lat_max and lng_min <= loc.longitude <= lng_max):
                    continue
                dist = haversine(vendor_lat, vendor_lng, loc.latitude, loc.longitude)
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
    background_tasks.add_task(offer_sequential(customer_lat, customer_lng, vendor_lat, vendor_lng), order_id)  # Assume setup for async background
    return {"order_id": order.id, "potential_offers": len(chosen)}

@router.post("/orders/{order_id}/accept/")
async def accept_order(order_id: str, user: User = Depends(get_current_user), redis = Depends(get_redis)):
    rider_profile = await RiderProfile.filter(user=user).first()
    if not rider_profile:
        raise HTTPException(403, "Not a rider")
    claim_key = f"order_claim:{order_id}"
    claimed = await redis.set(claim_key, str(user.id), nx=True, ex=30)
    if not claimed:
        raise HTTPException(status_code=400, detail="Order already claimed")
    offer = await OrderOffer.filter(order__id=order_id, rider=rider_profile, status="offered").first()
    if not offer:
        await redis.delete(claim_key)
        raise HTTPException(status_code=403, detail="Order not offered to this rider or already responded")
    if offer.expires_at < datetime.utcnow():
        await redis.delete(claim_key)
        raise HTTPException(400, "Offer expired")
    async with in_transaction() as conn:
        order = await Order.get(id=order_id).using_db(conn)
        if offer.status != "offered":
            await redis.delete(claim_key)
            raise HTTPException(status_code=400, detail="Order not available")
        order.status = OrderStatus.CONFIRMED
        order.metadata = order.metadata or {}
        order.metadata["rider_id"] = rider_profile.id
        order.accepted_at = datetime.utcnow()
        await order.save(using_db=conn)
        offer.status = "accepted"
        offer.responded_at = datetime.utcnow()
        offer.accepted_at = datetime.utcnow()
        await offer.save(using_db=conn)
        # Reject others if any
        await OrderOffer.filter(order=order).exclude(rider=rider_profile).update(status="rejected", responded_at=datetime.utcnow())
    # Update WorkDay
    today = date.today()
    workday, _ = await WorkDay.get_or_create(rider=rider_profile, date=today, defaults={"hours_worked": 0.0, "orders_accepted": 0})
    workday.orders_accepted += 1
    await workday.save()
    # Notify
    notify_payload = {
        "type": "order_accepted",
        "order_id": order_id,
        "rider_id": rider_profile.id,
        "accepted_at": datetime.utcnow().isoformat()
    }
    await redis.publish("order_updates", json.dumps(notify_payload))
    try:
        await manager.send_to(notify_payload, "customers", str(order.user_id))
    except:
        pass
    message = start_chat("riders", user.id, "customers", order.user_id)
    await redis.delete(claim_key)
    return {"status": "accepted", "order_id": order_id, "rider_id": rider_profile.id, "message": message} """

# @router.post("/orders/{order_id}/reject/")
# async def reject_order(order_id: str, body: RejectBody, user: User = Depends(get_current_user)):
#     rider_profile = await RiderProfile.filter(user=user).first()
#     if not rider_profile:
#         raise HTTPException(403, "Not a rider")
#     offer = await OrderOffer.filter(order__id=order_id, rider=rider_profile, status="offered").first()
#     if not offer:
#         raise HTTPException(status_code=403, detail="Order not offered to this rider or already responded")
#     if offer.expires_at < datetime.utcnow():
#         raise HTTPException(400, "Offer expired")
#     offer.status = "rejected"
#     offer.responded_at = datetime.utcnow()
#     offer.reason = body.reason
#     await offer.save()
#     return {"status": "rejected"}













""" @router.post("/orders/{order_id}/", status_code=201)
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
    return {"status": "rejected"} """





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

