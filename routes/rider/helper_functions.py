from app.utils.websocket_manager import manager
from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Dict
import uuid
from pydantic import BaseModel
from applications.customer.models import *
from applications.user.rider import RiderProfile as rider, Rating, Complaint, WorkDay, OrderOffer as Order
from applications.customer.models import Order as CustomerOrder



def start_chat(
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int
):
    if from_type not in {"riders", "customers", "vendors"} or to_type not in {"riders", "customers", "vendors"}:
        raise HTTPException(400, "Invalid user type")

    manager.start_chat(from_type, str(from_id), to_type, str(to_id))
    return {"status": "chat_started", "from": f"{from_type}:{from_id}", "to": f"{to_type}:{to_id}"}



def end_chat(
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int
):
    manager.end_chat(from_type, str(from_id), to_type, str(to_id))
    return {"status": "chat_ended"}




class OrderCreate(BaseModel):
    customer_name: str
    pickup_location: str
    pickup_distance_km: float
    pickup_time: datetime
    delivery_location: str
    eta_minutes: int
    payment_type: str
    order_type: str
    is_urgent: bool
    is_combined: bool = False
    combined_pickups: Optional[List[Dict[str, str]]] = None  # [{"name": "Restaurant1"}]

class OrderOut(BaseModel):
    id: uuid.UUID
    customer_name: str
    pickup_location: str
    pickup_distance_km: float
    pickup_time: datetime
    delivery_location: str
    eta_minutes: int
    payment_type: str
    order_type: str
    status: str
    is_urgent: bool
    payout: float
    base_rate: float
    distance_bonus: float
    is_combined: bool
    combined_pickups: Optional[List[Dict]]

class NotificationOut(BaseModel):
    id: uuid.UUID
    message: str
    type: str
    created_at: datetime
    is_read: bool

#***********************************************
#        Helper Function for Statistics
#***********************************************

def calculate_distance_bonus(distance: float) -> float:
    return max(distance - 3, 0) * 1

async def get_deliveries_count(rider: rider, start: datetime, end: datetime) -> int:
    orders = await Order.filter(
        rider=rider, status="accepted", accepted_at__gte=start, accepted_at__lt=end
    ).all()
    count = 0
    for order in orders:
        count += len(order.combined_pickups) if order.is_combined and order.combined_pickups else 1
    return count

async def get_delivery_pay(rider: rider, start: datetime, end: datetime) -> float:
    return await get_deliveries_count(rider, start, end) * 44

async def get_earnings(rider: rider, start: datetime, end: datetime) -> float:
    orders = await Order.filter(
        rider=rider, status="accepted", accepted_at__gte=start, accepted_at__lt=end
    ).all()
    
    return sum([order.base_rate + order.distance_bonus for order in orders])

async def get_monthly_rating(rider: rider, start: datetime, end: datetime) -> float:
    ratings = await Rating.filter(order__rider=rider, created_at__gte=start, created_at__lt=end).all()
    if not ratings:
        return 0.0
    return sum(r.score for r in ratings) / len(ratings)

async def get_monthly_rated_count(rider: rider, start: datetime, end: datetime) -> int:
    return await Rating.filter(order__rider=rider, created_at__gte=start, created_at__lt=end).count()

async def get_acceptance_rate(rider: rider, start: datetime, end: datetime) -> float:
    offered = await Order.filter(rider=rider, offered_at__gte=start, offered_at__lt=end).count()
    rejected = await Order.filter(rider=rider, offered_at__gte=start, offered_at__lt=end, status="rejected").count()
    if offered == 0:
        return 0.0
    return ((offered - rejected) / offered) * 100

async def get_on_time_rate(rider: rider, start: datetime, end: datetime) -> float:
    completed = await Order.filter(rider=rider, status="completed", completed_at__gte=start, completed_at__lt=end).count()
    on_time = await Order.filter(rider=rider, status="completed", completed_at__gte=start, completed_at__lt=end, is_on_time=True).count()
    if completed == 0:
        return 0.0
    return (on_time / completed) * 100

async def get_serious_complaints(rider: rider, start: datetime, end: datetime) -> int:
    return await Complaint.filter(order__rider=rider, is_serious=True, created_at__gte=start, created_at__lt=end).count()

async def get_excellence_bonus(rider: rider, start: datetime, end: datetime) -> float:
    deliveries = await get_deliveries_count(rider, start, end)
    #rated_count = await get_monthly_rated_count(rider, start, end)
    #rating = await get_monthly_rating(rider, start, end) if rated_count >= 20 else 4.0  # Waived if <20
    acceptance = await get_acceptance_rate(rider, start, end)
    on_time = await get_on_time_rate(rider, start, end)
    # complaints = await get_serious_complaints(rider, start, end)
    #if (deliveries >= 170 and rating >= 4.0 and acceptance >= 90 and on_time >= 92 and complaints == 0):
    if (deliveries >= 170 and acceptance >= 90 and on_time >= 92):
        return 2000.0
    return 0.0

async def get_weekly_bonuses(rider: rider, month_start: date, month_end: date) -> Dict:
    # Find first Monday in or before month
    first_day = datetime.combine(month_start, datetime.min.time())
    weekday = first_day.weekday()
    first_monday = first_day - timedelta(days=weekday)
    qualified_weeks = 0
    week_statuses = []
    i = 0
    while True:
        monday = first_monday + timedelta(weeks=i)
        saturday = monday + timedelta(days=5)
        if saturday < first_day or monday > datetime.combine(month_end, datetime.min.time()):
            break
        # Check if week overlaps month
        week_start = max(monday, first_day)
        week_end = min(saturday + timedelta(days=1), datetime.combine(month_end, datetime.min.time()) + timedelta(days=1))
        if week_start >= week_end:
            i += 1
            continue
        dates = [ (monday + timedelta(days=d)).date() for d in range(6) ]
        work_days = await WorkDay.filter(rider=rider, date__in=dates).all()
        work_days_dict = {wd.date: wd for wd in work_days}
        if len(work_days) != 6:
            status = "Not Qualified (Unscheduled absence)"
        else:
            qualified = True
            for d in dates:
                wd = work_days_dict.get(d)
                if not (wd.is_scheduled_leave or (wd.hours_worked >= 6 and wd.orders_accepted >= 1)):
                    qualified = False
                    break
            status = "Qualified" if qualified else "Not Qualified"
            if qualified:
                qualified_weeks += 1
        week_statuses.append({
            "week": i + 1,
            "status": status,
            "bonus": 400 if "Qualified" in status else 0
        })
        i += 1
    total_bonus = qualified_weeks * 400
    return {"total": total_bonus, "statuses": week_statuses}