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
from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum, VendorOrderConfirmation
from applications.items.models import Item
from applications.user.vendor import VendorProfile
from applications.user.customer import CustomerProfile
from tortoise.contrib.pydantic import pydantic_model_creator
from app.token import get_current_user
from app.utils.geo import haversine, bbox_for_radius, estimate_eta
from app.utils.websocket_manager import manager
from app.redis import get_redis
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError
from .notifications import send_notification, NotificationIn
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

        group_key = order.parent_order_id or order.id
        order_type = order.delivery_type.value   # "urgent", "split", "combined"

        async with in_transaction() as conn:
            # 1. Try to create confirmation – idempotent via unique constraint
            try:
                confirmation = await VendorOrderConfirmation.create(
                    group_key=group_key,
                    order=order,                     # link to this specific vendor's order
                    vendor=current_user,
                    using_db=conn,
                )
            except IntegrityError:
                # Already confirmed → can return early or treat as success
                confirmation = await VendorOrderConfirmation.get(
                    group_key=group_key,
                    vendor=current_user,
                    using_db=conn,
                )

            # 2. Count how many vendors have confirmed for this group
            # confirmed_count = await VendorOrderConfirmation.filter(
            #     group_key=group_key,
            #     confirmed=True
            # ).count(using_db=conn)

            confirmed_count = await (
                VendorOrderConfirmation
                .filter(group_key=group_key, confirmed=True)
                .using_db(conn)
                .count()
            )

            # 3. Get total vendors in group
            related_orders = await Order.filter(parent_order_id=group_key).all()
            if not related_orders:
                related_orders = [order]

            total_vendors = len(related_orders)
            all_confirmed = confirmed_count >= total_vendors

        # ────────────────────────────────────────────────
        # Now outside transaction – business logic
        # ────────────────────────────────────────────────

        print(f"order type : {order_type}")

        if order_type == "urgent" and all_confirmed:
            # Mark all related orders as CONFIRMED
            for o in related_orders:
                o.status = OrderStatus.CONFIRMED
                o.metadata = {**(o.metadata or {}), "all_vendors_confirmed": True}
                await o.save(update_fields=["status", "metadata"])

            vendor_profile = await VendorProfile.get_or_none(user=current_user)
            if vendor_profile:
                background_tasks.add_task(
                    _auto_assign_rider_for_urgent,
                    order.id,  # better to pass group_key
                    vendor_profile.latitude,
                    vendor_profile.longitude,
                    redis,
                )
            msg = "Order confirmed. Assigning nearest rider for urgent delivery..."

        elif order_type == "split":
            order.status = OrderStatus.CONFIRMED
            await order.save(update_fields=["status"])
            print(f"Order confirmation status {order.status}")

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
            msg = "Order confirmed. Finding available riders..."

        elif order_type == "combined" and all_confirmed:
            for o in related_orders:
                o.status = OrderStatus.CONFIRMED
                o.metadata = {**(o.metadata or {}), "all_vendors_confirmed": True}
                await o.save(update_fields=["status", "metadata"])

            vendor_profile = await VendorProfile.get_or_none(user=current_user)
            if vendor_profile:
                broadcast_id = group_key
                background_tasks.add_task(
                    _broadcast_rider_offers,
                    broadcast_id,
                    vendor_profile.latitude,
                    vendor_profile.longitude,
                    is_urgent=False,
                    redis=redis,
                )
            msg = "All vendors confirmed. Finding available riders..."

        elif order_type in ("combined", "urgent") and not all_confirmed:
            # Optional: update this order to PROCESSING
            order.status = OrderStatus.PROCESSING
            await order.save(update_fields=["status"])
            pending = total_vendors - confirmed_count
            msg = f"Order confirmed. Waiting for {pending} more vendor(s)..."

        else:
            order.status = OrderStatus.CONFIRMED
            await order.save(update_fields=["status"])
            msg = "Order confirmed successfully"

        # Notifications (same as before)...
        if order_type != "urgent":
            try:
                await send_notification(NotificationIn(
                    user_id=order.user_id,
                    title="Vendor Confirmed",
                    body=f"Vendor confirmed order #{order.id}",
                ))

                await manager.send_notification(
                    "customers",
                    str(order.user_id),
                    "Order confirm by vandor",
                    "Your order has been confirmed"
                )
            except Exception as e:
                print(f"[CONFIRM] Notification error: {e}")

        # pending_vendors = (
        #     len(related_orders) - len(vendor_confirmations)
        #     if order_type == "combined"
        #     else 0
        # )

        return {
            "success": True,
            "message": msg,
            "data": {
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "order_type": order_type,
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                "vendor_id": current_user.id,
                "vendor_name": current_user.name,
                "all_vendors_confirmed": all_confirmed,
                "confirmed_count": confirmed_count,
                "total_vendors": total_vendors,
                "pending_vendors": total_vendors - confirmed_count,
                "next_action": (
                    "Waiting for available rider" if all_confirmed else "Waiting for other vendors"
                ) if order_type in ("combined", "urgent") else None,
            }
        }
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
            "user", "items__item", "vendor", "rider__user"
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        rider_info = {
                "rider_id": rider_profile.user_id,
                "rider_name": current_user.name,
                "rider_phone": current_user.phone,
                "rider_image": rider_profile.profile_image
            }
        
        order.metadata["rider_info"] = order.metadata.get("rider_info", {}) if order.metadata else {}
        order.metadata["rider_info"].update(rider_info)
        await order.save()


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
                "vendor", "user", "rider"
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
            o.status = OrderStatus.PREPARED

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
            order.rider = rider_profile
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
                    await send_notification(NotificationIn(
                        o.vendor_id,
                        "Rider Assigned",
                        f"Rider {current_user.name} assigned to order #{o.id}",
                    ))

                await manager.send_notification(
                    "vendors",
                    str(o.vendor_id),
                    "Rider assigned",
                    f"{current_user.name} assigned to your order #{o.id}",
                )

            # Notify customer (combined info)
            await send_notification(NotificationIn(
                order.user_id,
                "Rider Assigned",
                f"Rider {current_user.name} is picking up your order(s)",
            ))

            await manager.send_notification(
                "customers",
                str(order.user_id),
                "Rider Assigned",
                f"Rider {current_user.name} is picking up your order(s)"
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

                await send_notification(NotificationIn(
                    rider_profile.user_id,
                    "Combined Order Accepted",
                    f"You accepted {len(group_orders)} combined orders. Total payout ₹{base_rate + distance_bonus:.2f}.",
                ))

                await manager.send_to(
                    "riders",
                    str(rider_profile.user_id),
                    "Combined Order Accepted",
                    f"You accepted {len(group_orders)} combined orders. Total payout ₹{base_rate + distance_bonus:.2f}."
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

@router.post("/rider/reject/{order_id}/")
async def reject_order(
    request: Request,
    order_id: str,
    reject_data: OrderRejectRequest,
    current_user: User = Depends(get_current_user)
):
    """RIDER rejects an order offer."""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    try:
        rider_profile = await RiderProfile.get_or_none(user=current_user)
        if not rider_profile:
            raise HTTPException(status_code=403, detail="Not a rider profile")
        
        order = await Order.get_or_none(id=order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Find and update offer
        offer = await OrderOffer.get_or_none(order__parent_order_id=order.parent_order_id, rider=rider_profile)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        if offer.status != "PENDING":
            raise HTTPException(status_code=400, detail="Can only reject pending offers")
        
        offer.status = "REJECTED"
        offer.reject_reason = reject_data.reason
        offer.responded_at = datetime.utcnow()
        await offer.save()
        
        # Update WorkDay stats
        today = date.today()
        workday, _ = await WorkDay.get_or_create(
            rider=rider_profile,
            date=today,
            defaults={"hours_worked": 0.0, "rejection_count": 0}
        )
        workday.rejection_count += 1
        await workday.save()
        
        logger.info(f"Rider {rider_profile.id} rejected order {order_id}: {reject_data.reason}")
        
        return translate({
            "success": True,
            "message": "Order rejected",
            "order_id": order_id
        }, lang)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

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

# async def _check_all_vendors_confirmed(related_orders: list[Order], metadata: dict) -> bool:
#     vendor_confirmations = metadata.get("vendor_confirmations", {})
#     vendor_ids = {o.vendor_id for o in related_orders}
#     confirmed_vendors = set(int(v) for v in vendor_confirmations.keys())
#     print("================================================================")
#     print(f"Vendors: {vendor_ids}, Confirmed: {confirmed_vendors}")
#     print("================================================================")
#     return vendor_ids == confirmed_vendors


async def _auto_assign_rider_for_urgent(
    order_id: str,
    vendor_lat: float,
    vendor_lng: float,
    redis,
):
    try:
        order = await Order.get_or_none(id=order_id)
        if not order:
            order = await Order.filter(parent_order_id=order_id).first()
            orders = await Order.filter(parent_order_id=order_id).all()

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
            assigned_rider = None
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
            print(f"[AUTO_ASSIGN] Checking rider {rider_profile.id}, active orders: {active_orders}")
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
            await send_notification(NotificationIn(
                user_id=assigned_rider.user_id,
                title="🚨 URGENT ORDER ASSIGNED",
                body=f"Urgent order #{order.id} assigned. Pick up immediately!",
            ))
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
    print(f"[BROADCAST] Broadcasting order {order_id} offers to riders")
    try:
        print(f"[BROADCAST] Finding order {order_id}")
        orders = None
        order = await Order.get_or_none(id=order_id)
        if not order:
            print(f"[BROADCAST] Order {order_id} not found")
            order = await Order.filter(parent_order_id=order_id).first()
            orders = await Order.filter(parent_order_id=order_id).all().prefetch_related("user", "items__item", "vendor")
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
                    total = 0.0
                    result = []
                    if orders:
                        for o in orders:
                            total += float(o.total)
                            items = []
                            for oi in o.items:
                                items.append({
                                    "item_id": oi.item_id,
                                    "title": oi.title,
                                    "price": oi.price,
                                    "quantity": oi.quantity
                                })
                            payload = {
                                "order_id": o.id,
                                "vandor_name": o.vendor.name if o.vendor else "Store",
                                "items": items
                            }
                            result.append(payload)
                        # paren_order_id = order.parent_order_id
                    else:
                        total = float(order.total)
                        result = [{
                            "order_id": order.id,
                            "vandor_name": order.vendor.name if order.vendor else "Store",
                            "items": order.items if order.items else []
                        }]

                    # cust_info = {
                    #     "customer_name": order.user.name,
                    #     "customer_phone": order.user.phone,
                    #     "customer_id": order.user_id
                    # }

                    # print(f"cust_info: {cust_info}")
                    
                    print(f"rider user id {rider.user_id}")
                    await manager.send_notification(
                        "riders",
                        rider.user_id,
                        "New Order Offer",
                        f"result: {result}, Total Amount: ₹{total}, parent_order_id: {order.parent_order_id if order.parent_order_id else order.id}",
                    )
                except Exception:
                    pass

                try:
                    await send_notification(NotificationIn(
                        user_id=rider.user_id,
                        title="New Order Offer",
                        body=f"Order #{order_id} - ₹{order.total}",
                    ))
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
        query = Order.filter(rider=rider_profile, status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.PREPARED, OrderStatus.OUT_FOR_DELIVERY]).prefetch_related("user", "items__item", "vendor")
        
        # if status_filter:
        #     try:
        #         #status_enum = [OrderStatus[statuss.upper()] for statuss in status_filter]
        #         query = query.filter(status__in=[OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.PREPARED, OrderStatus.OUT_FOR_DELIVERY])
        #     except KeyError:
        #         raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        
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
                "customer_id": order.user_id,
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
    


@router.get("/rider/orders-by-status/")
async def get_rider_orders_by_status(
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
                "customer_id": order.user_id,
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
                "customer_id": order.user_id,
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

# @router.post("/cancel/{order_id}/")
# async def cancel_order(
#     request: Request,
#     order_id: str,
#     cancel_data: CancelOrderRequest,
#     current_user: User = Depends(get_current_user)
# ):
#     """
#     Cancel an order (by customer, rider, or vendor).
    
#     Rules:
#     - Customer can cancel PENDING/PROCESSING/CONFIRMED orders
#     - Rider can cancel PROCESSING/CONFIRMED orders
#     - Vendor can cancel PROCESSING/CONFIRMED orders
#     - Cannot cancel SHIPPED/OUT_FOR_DELIVERY/DELIVERED
#     - If paid, mark for refund
#     """
#     lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
#     try:
#         order = await Order.get_or_none(id=order_id).prefetch_related("user", "rider", "items__item")
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
        
#         # Authorization check
#         is_customer = order.user_id == current_user.id
#         is_rider = order.rider and order.rider.user_id == current_user.id
#         is_vendor = current_user.is_vendor
        
#         if not (is_customer or is_rider or is_vendor):
#             raise HTTPException(status_code=403, detail="Not authorized to cancel this order")
        
#         # Check cancellable status
#         current_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
#         cancellable_statuses = ["pending", "processing", "confirmed"]
        
#         if current_status.lower() not in cancellable_statuses:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot cancel order with status: {current_status}"
#             )
        
#         # If paid, mark for refund
#         if order.payment_status == "paid":
#             if order.metadata is None:
#                 order.metadata = {}
#             order.metadata["refund_requested"] = True
#             order.metadata["refund_requested_at"] = datetime.utcnow().isoformat()
#             order.metadata["refund_reason"] = cancel_data.reason or "User cancelled"
        
#         # Update order
#         old_status = current_status
#         order.status = OrderStatus.CANCELLED
#         order.reason = cancel_data.reason or "Cancelled"
#         order.updated_at = datetime.utcnow()
#         await order.save()
        
#         # Send notifications
#         try:
#             # Notify customer
#             await send_notification(
#                 order.user_id,
#                 "Order Cancelled",
#                 f"Your order #{order_id} has been cancelled. Reason: {order.reason}"
#             )
            
#             # Notify rider
#             if order.rider:
#                 await send_notification(
#                     order.rider.user_id,
#                     "Order Cancelled",
#                     f"Order #{order_id} has been cancelled."
#                 )
            
#             # Notify vendors
#             vendor_ids = set()
#             for oi in order.items:
#                 vendor_ids.add(oi.item.vendor_id)
            
#             for vendor_id in vendor_ids:
#                 vendor = await VendorProfile.get_or_none(id=vendor_id)
#                 if vendor:
#                     await send_notification(
#                         vendor.user_id,
#                         "Order Cancelled",
#                         f"Order #{order_id} has been cancelled."
#                     )
#         except Exception as e:
#             logger.warning(f"Notification error: {str(e)}")
        
#         return translate({
#             "success": True,
#             "message": "Order cancelled successfully",
#             "data": {
#                 "order_id": order_id,
#                 "old_status": old_status,
#                 "new_status": "cancelled",
#                 "refund_requested": order.payment_status == "paid"
#             }
#         }, lang)
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error cancelling order: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

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
            await send_notification(NotificationIn(
                user_id=order.rider.user_id,
                title="Order Ready",
                body=f"Order #{order_id} is ready for pickup"
            ))
        
        await send_notification(NotificationIn(
            user_id=order.user_id,
            title="Order Shipped",
            body=f"Your order #{order_id} has been handed to the rider"
        ))
        
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
        await send_notification(NotificationIn(
            user_id=order.user_id,
            title="Order On The Way",
            body=f"Your order #{order_id} is on the way"
        ))
        
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
        orders = await Order.filter(parent_order_id=order.parent_order_id).all()
        deliverable_orders = [ord for ord in orders if ord.status == OrderStatus.OUT_FOR_DELIVERY]

        if len(deliverable_orders) != len(orders):
            raise HTTPException(
                status_code=400,
                detail=f"All orders under parent order ID {order.parent_order_id} must be OUT_FOR_DELIVERY to mark as delivered"
            )

        for ord in orders:
            ord.status = OrderStatus.DELIVERED
            ord.completed_at = datetime.utcnow()
            await ord.save()
        
        # order.status = OrderStatus.DELIVERED
        # order.completed_at = datetime.utcnow()
        # await order.save()
        
        # Notify customer
        await send_notification(NotificationIn(
            order.user_id,
            "Order Delivered",
            f"Your order #{order_id} has been delivered successfully"
        ))
        
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
            order_info = []
            orders = await Order.filter(parent_order_id=order.parent_order_id).all().prefetch_related("items__item", "user", "vendor")
            for order in orders:
                for oi in order.items:
                    items.append({
                        "item_id": oi.item_id,
                        "title": oi.title,
                        "price": oi.price,
                        "quantity": oi.quantity
                    })
                order_info.append({
                    "order_id": order.id,
                    "vendor_name": order.vendor.name if order.vendor else None,
                    "items": items
                })

            
            result.append({
                "offer_id": offer.id,
                "order_id": order.id,
                "parent_order_id": order.parent_order_id,
                "customer_name": order.user.name,
                "customer_phone": order.user.phone,
                "customer_id": order.user.id,
                "order_info": order_info,
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
    







