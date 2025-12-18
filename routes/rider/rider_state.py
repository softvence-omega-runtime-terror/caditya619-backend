from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict
from decimal import Decimal
from pydantic import BaseModel
import logging
from dateutil.relativedelta import relativedelta
import pytz

from applications.user.models import User
from applications.user.rider import (
    RiderProfile, WorkDay, RiderFeesAndBonuses, PushNotification,
    Complaint, RiderReview, RiderCurrentLocation
)
from applications.customer.models import Order, OrderStatus, OrderItem, DeliveryTypeEnum
from applications.items.models import Item
from applications.user.vendor import VendorProfile
from app.token import get_current_user
from app.utils.translator import translate
from app.utils.websocket_manager import manager
from app.redis import get_redis
from .notifications import send_notification
from .helper_functions import to_float
from math import ceil, floor

logger = logging.getLogger(__name__)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class RiderStatsRequest(BaseModel):
    period: str  # "day", "week", "month", "year"

class RiderStatsResponse(BaseModel):
    total_deliveries: int
    earnings_today: float
    earnings_this_week: float
    earnings_this_month: float
    customer_rating: float
    acceptance_rate: float
    on_time_rate: float
    is_online: bool
    current_balance: float
    
class MonthlyStatsResponse(BaseModel):
    delivery_pay: float
    weekly_bonuses: float
    excellence_bonus: float
    subtotal_earned: float
    guarantee_topup: float
    final_earnings: float
    monthly_breakdown: Dict

class WeeklyStatsResponse(BaseModel):
    week_number: int
    days_worked: int
    hours_worked: float
    deliveries: int
    delivery_pay: float
    weekly_bonus_status: str
    projected_total: float

class AnnualStatsResponse(BaseModel):
    total_deliveries: int
    total_earnings: float
    average_monthly: float
    best_month: Dict
    month_breakdown: List[Dict]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
    

async def get_total_earnings(rider: RiderProfile) -> float:
    orders = await Order.filter(
        rider=rider, status="delivered"
    ).all()
    
    return sum([order.base_rate + order.distance_bonus for order in orders])


async def get_total_acceptance_rate(rider: RiderProfile) -> float:
    offered = await WorkDay.filter(rider=rider)
    offered_count = 0
    for offer in offered:
        offered_count += offer.order_offer_count
    
    accepted = await Order.filter(rider=rider, status="delivered").count()
   
    if offered_count == 0:
        return 0.0
    acceptance_rate = (to_float(accepted) / to_float(offered_count)) * 100.0
    
    return acceptance_rate

async def get_deliveries_count(rider: RiderProfile, start: datetime, end: datetime) -> int:
    """Get count of completed deliveries including combined order pickups"""
    orders = await Order.filter(
        rider=rider,
        status=OrderStatus.DELIVERED,
        completed_at__gte=start,
        completed_at__lte=end
    ).all()
    
    count = 0
    for order in orders:
        if order.is_combined and order.combined_pickups:
            count += len(order.combined_pickups)
        else:
            count += 1
    return count

async def get_delivery_earnings(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Calculate delivery earnings based on base rate only"""
    feesandbonus = await RiderFeesAndBonuses.get_or_none(id=1)
    if not feesandbonus:
        feesandbonus = await RiderFeesAndBonuses.create(
            rider_base_salary=8000.00,
            rider_delivery_fee=44.00,
            distance_bonus_per_km=1.00,
            weekly_bonus=400.00,
            excellence_bonus=2000.00
        )
    
    orders = await Order.filter(
        rider=rider,
        status=OrderStatus.DELIVERED,
        completed_at__gte=start,
        completed_at__lte=end
    ).all()
    
    total = 0.0
    for order in orders:
        total += float(order.base_rate or 44.00)
        if order.is_combined and order.combined_pickups:
            # Each additional pickup gets base rate
            total += (len(order.combined_pickups) - 1) * float(feesandbonus.rider_delivery_fee)
    
    return total

async def get_distance_bonus(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Calculate distance bonuses"""
    orders = await Order.filter(
        rider=rider,
        status=OrderStatus.DELIVERED,
        completed_at__gte=start,
        completed_at__lte=end
    ).all()
    
    return sum(float(order.distance_bonus or 0.0) for order in orders)

async def get_monthly_rating(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Get average customer rating for the period"""
    reviews = await RiderReview.filter(
        rider=rider,
        created_at__gte=start,
        created_at__lte=end
    ).all()
    
    if not reviews:
        return 0.0
    
    total_rating = sum(r.rating for r in reviews)
    return round(total_rating / len(reviews), 2)

async def get_rated_orders_count(rider: RiderProfile, start: datetime, end: datetime) -> int:
    """Get count of orders that were rated"""
    return await RiderReview.filter(
        rider=rider,
        created_at__gte=start,
        created_at__lte=end
    ).count()

async def get_acceptance_rate(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Calculate acceptance rate percentage"""
    start_date = start.date()
    end_date = end.date()
    
    # Get all work days in period
    work_days = await WorkDay.filter(
        rider=rider,
        date__gte=start_date,
        date__lt=end_date
    ).all()
    
    # Count total offers
    total_offers = sum(wd.order_offer_count for wd in work_days)
    
    if total_offers == 0:
        return 0.0
    
    # Count accepted/delivered orders
    accepted_orders = await Order.filter(
        rider=rider,
        accepted_at__gte=start,
        accepted_at__lt=end,
        status=OrderStatus.DELIVERED
    ).count()
    
    rate = (to_float(accepted_orders) / to_float(total_offers)) * 100.0
    return round(rate, 2)

async def get_on_time_rate(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Calculate on-time delivery rate percentage"""
    completed = await Order.filter(
        rider=rider,
        status=OrderStatus.DELIVERED,
        completed_at__gte=start,
        completed_at__lt=end
    ).count()
    
    if completed == 0:
        return 0.0
    
    on_time = await Order.filter(
        rider=rider,
        status=OrderStatus.DELIVERED,
        completed_at__gte=start,
        completed_at__lt=end,
        is_on_time=True
    ).count()
    
    rate = (to_float(on_time) / to_float(completed)) * 100.0
    return round(rate, 2)

async def get_serious_complaints_count(rider: RiderProfile, start: datetime, end: datetime) -> int:
    """Get count of serious complaints"""
    return await Complaint.filter(
        rider=rider,
        is_serious=True,
        created_at__gte=start,
        created_at__lt=end
    ).count()

async def calculate_excellence_bonus(rider: RiderProfile, start: datetime, end: datetime) -> float:
    """Calculate excellence bonus based on 5 criteria"""
    deliveries = await get_deliveries_count(rider, start, end)
    rated_count = await get_rated_orders_count(rider, start, end)
    rating = await get_monthly_rating(rider, start, end)
    acceptance = await get_acceptance_rate(rider, start, end)
    on_time = await get_on_time_rate(rider, start, end)
    complaints = await get_serious_complaints_count(rider, start, end)
    
    # Check all 5 criteria
    criteria_met = 0
    
    if deliveries >= 170:
        criteria_met += 1
    
    # Rating criterion waived if <20 reviews
    if rated_count < 20:
        criteria_met += 1  # Auto-pass
    elif rating >= 4.0:
        criteria_met += 1
    
    if acceptance >= 90.0:
        criteria_met += 1
    
    if on_time >= 92.0:
        criteria_met += 1
    
    if complaints == 0:
        criteria_met += 1
    
    feesandbonus = await RiderFeesAndBonuses.get_or_none(id=1)
    if not feesandbonus:
        feesandbonus = await RiderFeesAndBonuses.create()
    
    # All 5 criteria must be met
    if criteria_met == 5:
        return float(feesandbonus.excellence_bonus or 2000.00)
    
    return 0.0

async def get_weekly_bonuses(rider: RiderProfile, month_start: date, month_end: date) -> Dict:
    """Calculate weekly bonuses for the month"""
    feesandbonus = await RiderFeesAndBonuses.get_or_none(id=1)
    if not feesandbonus:
        feesandbonus = await RiderFeesAndBonuses.create()
    
    # Find first Monday on or before month start
    first_day_dt = datetime.combine(month_start, datetime.min.time())
    weekday = first_day_dt.weekday()  # 0=Monday, 6=Sunday
    first_monday = first_day_dt - timedelta(days=weekday)
    
    qualified_weeks = 0
    week_statuses = []
    week_num = 0
    
    while True:
        monday = first_monday + timedelta(weeks=week_num)
        saturday = monday + timedelta(days=5)
        
        # Check if week is outside month range
        if saturday.date() < month_start or monday.date() > month_end:
            break
        
        # Get dates for this week (Mon-Sat)
        dates = [(monday + timedelta(days=d)).date() for d in range(6)]
        
        # Get work days for this week
        work_days = await WorkDay.filter(
            rider=rider,
            date__in=dates
        ).all()
        
        work_days_dict = {wd.date: wd for wd in work_days}
        
        # Check qualification: all 6 days with 6+ hours and at least 1 order
        is_qualified = True
        days_worked = 0
        
        for d in dates:
            wd = work_days_dict.get(d)
            if wd:
                if wd.is_scheduled_leave:
                    continue  # Scheduled leave doesn't disqualify
                if wd.hours_worked >= 6.0 and wd.order_offer_count >= 1:
                    days_worked += 1
                else:
                    is_qualified = False
                    break
            else:
                is_qualified = False
                break
        
        # Must have all 6 days worked
        if days_worked == 6 and is_qualified:
            qualified_weeks += 1
            status = "Qualified"
            bonus = float(feesandbonus.weekly_bonus or 400.00)
        else:
            status = "Not Qualified"
            bonus = 0.0
        
        week_statuses.append({
            "week": week_num + 1,
            "status": status,
            "bonus": bonus,
            "days_worked": days_worked
        })
        
        week_num += 1
    
    total_bonus = qualified_weeks * float(feesandbonus.weekly_bonus or 400.00)
    # Maximum 4 weeks
    total_bonus = min(total_bonus, 1600.00)
    
    return {
        "total": total_bonus,
        "qualified_weeks": qualified_weeks,
        "statuses": week_statuses
    }

async def calculate_monthly_earnings(rider: RiderProfile, month_start: date, month_end: date) -> Dict:
    """Calculate complete monthly earnings with all components"""
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    month_end_dt = datetime.combine(month_end, datetime.max.time())
    
    # Get fees configuration
    feesandbonus = await RiderFeesAndBonuses.get_or_none(id=1)
    if not feesandbonus:
        feesandbonus = await RiderFeesAndBonuses.create()
    
    # Step 1: Delivery Pay
    delivery_pay = await get_delivery_earnings(rider, month_start_dt, month_end_dt)
    distance_bonus = await get_distance_bonus(rider, month_start_dt, month_end_dt)
    
    # Step 2: Weekly Bonuses
    weekly_data = await get_weekly_bonuses(rider, month_start, month_end)
    weekly_bonuses = weekly_data["total"]
    
    # Step 3: Excellence Bonus
    excellence_bonus = await calculate_excellence_bonus(rider, month_start_dt, month_end_dt)
    
    # Step 4: Subtotal
    subtotal = delivery_pay + distance_bonus + weekly_bonuses + excellence_bonus
    
    # Step 5: Apply Guarantee Floor (₹8,000)
    guarantee_floor = float(feesandbonus.rider_base_salary or 8000.00)
    guarantee_topup = 0.0
    final_earnings = subtotal

    if subtotal == 0.0:
        guarantee_topup = guarantee_floor
        final_earnings = 0.0
    
    elif subtotal < guarantee_floor:
        guarantee_topup = guarantee_floor - subtotal
        final_earnings = guarantee_floor
    
    return {
        "delivery_pay": round(delivery_pay, 2),
        "distance_bonus": round(distance_bonus, 2),
        "weekly_bonuses": round(weekly_bonuses, 2),
        "excellence_bonus": round(excellence_bonus, 2),
        "subtotal_earned": round(subtotal, 2),
        "guarantee_topup": round(guarantee_topup, 2),
        "final_earnings": round(final_earnings, 2),
        "weekly_details": weekly_data["statuses"]
    }

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(tags=['Rider Statistics'])

@router.get("/rider/stats/", response_model=RiderStatsResponse)
async def get_rider_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get real-time rider statistics"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    now = datetime.utcnow()
    today = now.date()
    
    # Today
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    earnings_today = await get_delivery_earnings(rider, today_start, today_end) + \
                     await get_distance_bonus(rider, today_start, today_end)
    deliveries_today = await get_deliveries_count(rider, today_start, today_end)
    
    # This week (Monday to Sunday)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(week_end, datetime.max.time())
    earnings_this_week = await get_delivery_earnings(rider, week_start_dt, week_end_dt) + \
                         await get_distance_bonus(rider, week_start_dt, week_end_dt)
    deliveries_this_week = await get_deliveries_count(rider, week_start_dt, week_end_dt)
    
    # This month
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    month_end_dt = datetime.combine(month_end, datetime.max.time())
    earnings_this_month = await get_delivery_earnings(rider, month_start_dt, month_end_dt) + \
                          await get_distance_bonus(rider, month_start_dt, month_end_dt)
    
    # Ratings and acceptance
    rating = await get_monthly_rating(rider, month_start_dt, month_end_dt)
    acceptance_rate = await get_acceptance_rate(rider, month_start_dt, month_end_dt)
    on_time_rate = await get_on_time_rate(rider, month_start_dt, month_end_dt)
    
    return translate(RiderStatsResponse(
        total_deliveries=deliveries_this_week,
        earnings_today=round(earnings_today, 2),
        earnings_this_week=round(earnings_this_week, 2),
        earnings_this_month=round(earnings_this_month, 2),
        customer_rating=rating,
        acceptance_rate=acceptance_rate,
        on_time_rate=on_time_rate,
        is_online=rider.is_available,
        current_balance=float(rider.current_balance or 0.0)
    ), lang)

@router.get("/rider/stats/monthly/", response_model=MonthlyStatsResponse)
async def get_monthly_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get detailed monthly earnings breakdown"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    earnings = await calculate_monthly_earnings(rider, month_start, month_end)
    
    return translate(MonthlyStatsResponse(
        delivery_pay=earnings["delivery_pay"],
        weekly_bonuses=earnings["weekly_bonuses"],
        excellence_bonus=earnings["excellence_bonus"],
        subtotal_earned=earnings["subtotal_earned"],
        guarantee_topup=earnings["guarantee_topup"],
        final_earnings=earnings["final_earnings"],
        monthly_breakdown=earnings
    ), lang)

@router.get("/rider/stats/weekly/", response_model=WeeklyStatsResponse)
async def get_weekly_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get weekly earnings breakdown"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    now = datetime.utcnow()
    today = now.date()
    
    # This week
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=5)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(week_end, datetime.max.time())
    
    # Get work days
    work_days = await WorkDay.filter(
        rider=rider,
        date__gte=week_start,
        date__lte=week_end
    ).all()
    
    days_worked = len([wd for wd in work_days if wd.hours_worked >= 6])
    hours_worked = sum(wd.hours_worked for wd in work_days)
    
    deliveries = await get_deliveries_count(rider, week_start_dt, week_end_dt)
    delivery_pay = await get_delivery_earnings(rider, week_start_dt, week_end_dt) + \
                   await get_distance_bonus(rider, week_start_dt, week_end_dt)
    
    # Check bonus status
    feesandbonus = await RiderFeesAndBonuses.get_or_none(id=1)
    if not feesandbonus:
        feesandbonus = await RiderFeesAndBonuses.create()
    
    if days_worked == 6:
        weekly_bonus_status = "Qualified"
        bonus = float(feesandbonus.weekly_bonus or 400.00)
    else:
        weekly_bonus_status = f"{days_worked}/6 days"
        bonus = 0.0
    
    projected_total = delivery_pay + bonus
    
    week_num = (today - week_start).days // 7 + 1
    
    return translate(WeeklyStatsResponse(
        week_number=week_num,
        days_worked=days_worked,
        hours_worked=round(hours_worked, 2),
        deliveries=deliveries,
        delivery_pay=round(delivery_pay, 2),
        weekly_bonus_status=weekly_bonus_status,
        projected_total=round(projected_total, 2)
    ), lang)

@router.get("/rider/stats/annual/", response_model=AnnualStatsResponse)
async def get_annual_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get year-to-date statistics"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    today = datetime.utcnow().date()
    year_start = today.replace(month=1, day=1)
    
    # Get all months in current year
    month_breakdown = []
    best_month = {"month": "", "earnings": 0.0}
    total_deliveries = 0
    total_earnings = 0.0
    
    for month_num in range(1, today.month + 1):
        month_start = today.replace(month=month_num, day=1)
        
        if month_num == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=month_num + 1, day=1) - timedelta(days=1)
        
        if month_end > today:
            month_end = today
        
        month_start_dt = datetime.combine(month_start, datetime.min.time())
        month_end_dt = datetime.combine(month_end, datetime.max.time())
        
        month_deliveries = await get_deliveries_count(rider, month_start_dt, month_end_dt)
        earnings = await calculate_monthly_earnings(rider, month_start, month_end)
        month_earnings = earnings["final_earnings"]
        
        month_name = month_start.strftime("%B")
        month_breakdown.append({
            "month": month_name,
            "month_num": month_num,
            "deliveries": month_deliveries,
            "earnings": month_earnings
        })
        
        total_deliveries += month_deliveries
        total_earnings += month_earnings
        
        if month_earnings > best_month["earnings"]:
            best_month = {
                "month": month_name,
                "earnings": month_earnings,
                "deliveries": month_deliveries
            }
    
    average_monthly = total_earnings / len(month_breakdown) if month_breakdown else 0.0
    
    return translate(AnnualStatsResponse(
        total_deliveries=total_deliveries,
        total_earnings=round(total_earnings, 2),
        average_monthly=round(average_monthly, 2),
        best_month=best_month,
        month_breakdown=month_breakdown
    ), lang)

@router.get("/rider/bonus-progress/")
async def get_bonus_progress(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get excellence bonus progress details"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    month_end_dt = datetime.combine(month_end, datetime.max.time())
    
    # Get all criteria
    deliveries = await get_deliveries_count(rider, month_start_dt, month_end_dt)
    rated_count = await get_rated_orders_count(rider, month_start_dt, month_end_dt)
    rating = await get_monthly_rating(rider, month_start_dt, month_end_dt)
    acceptance = await get_acceptance_rate(rider, month_start_dt, month_end_dt)
    on_time = await get_on_time_rate(rider, month_start_dt, month_end_dt)
    complaints = await get_serious_complaints_count(rider, month_start_dt, month_end_dt)
    
    criteria = [
        {
            "name": "Deliveries",
            "required": 170,
            "current": deliveries,
            "met": deliveries >= 170
        },
        {
            "name": "Rating",
            "required": 4.0,
            "current": rating,
            "met": rating >= 4.0 if rated_count >= 20 else True,
            "note": f"Waived (only {rated_count}/20 ratings)" if rated_count < 20 else ""
        },
        {
            "name": "Acceptance Rate",
            "required": 90.0,
            "current": acceptance,
            "met": acceptance >= 90.0
        },
        {
            "name": "On-Time Rate",
            "required": 92.0,
            "current": on_time,
            "met": on_time >= 92.0
        },
        {
            "name": "Serious Complaints",
            "required": 0,
            "current": complaints,
            "met": complaints == 0
        }
    ]
    
    criteria_met = sum(1 for c in criteria if c["met"])
    eligible = criteria_met == 5
    
    return translate({
        "month": month_start.strftime("%B %Y"),
        "criteria": criteria,
        "criteria_met": criteria_met,
        "total_criteria": 5,
        "eligible_for_bonus": eligible,
        "bonus_amount": 2000.0 if eligible else 0.0
    }, lang)





@router.get("/rider-monthly-forecast/")
async def get_rider_monthly_forecast(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get forecast of monthly earnings based on recent performance"""
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    earnings = await calculate_monthly_earnings(rider, month_start, month_end)
    subtotal = earnings["subtotal_earned"]

    target = 14000
    percentage = (subtotal / target) * 100
    remaining_deliveries = max((target - subtotal) / 44, 0)
    if remaining_deliveries > floor(remaining_deliveries):
        remaining_deliveries = ceil(remaining_deliveries)
    else:
        remaining_deliveries = floor(remaining_deliveries)


    return translate({
        "subtotal": round(subtotal, 2),
        "percentage": round(percentage, 2),
        "remaining_deliveries": round(remaining_deliveries, 2),
        "target": round(target, 2)
        }, lang)






@router.get("/leaderboard/")
async def get_leaderboard(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get(user=user)
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = month_start + relativedelta(months=1)
    all_riders = await RiderProfile.all()
    scores = []
    for p in all_riders:
        deliveries = await get_deliveries_count(p, month_start, month_end)
        rating = await get_monthly_rating(p, month_start, month_end)
        on_time = await get_on_time_rate(p, month_start, month_end)
        score = (deliveries * 0.5) + (rating * 50) + (on_time * 2)
        scores.append((p.id, score, deliveries, rating, on_time))
    scores.sort(key=lambda x: x[1], reverse=True)
    rank = next((i+1 for i, s in enumerate(scores) if s[0] == rider.id), None)
    total_riders = len(scores)
    my_score, my_deliveries, my_rating, my_on_time = next((s for s in scores if s[0] == rider.id), (0,0,0,0))[1:]
    prize_structure = {1: 2000, 2: 1000, 3: 500}
    prize = prize_structure.get(rank, 250 if rank <= 10 else 0)
    return translate({
        "rank": rank,
        "total_riders": total_riders,
        "total_deliveries": my_deliveries,
        "prize_money": prize,
        "score": my_score,
        "breakdown": {
            "deliveries_pts": my_deliveries * 0.5,
            "rating_pts": my_rating * 50,
            "on_time_pts": my_on_time * 2
        }
    }, lang)



@router.get("/rider-current-tire/")
async def get_rider_tires(request: Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=current_user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider not found")
    today = datetime.now(pytz.UTC)
    created_at = rider_profile.created_at
    if created_at.tzinfo is None:
        created_at = pytz.UTC.localize(created_at)
    #today = datetime.utcnow()
    month_of_work = relativedelta(today, created_at).years * 12 + \
                    relativedelta(today, created_at).months

    earnings = await get_total_earnings(rider_profile)
    qs = RiderReview.filter(rider=rider_profile, rating__not_isnull=True)
    # get list of rating values
    ratings = await qs.values_list("rating", flat=True)  # returns list of Decimal/float

    total_reviews = len(ratings)
    if total_reviews == 0:
        avg_rating = 0.0
    else:
        # Convert to float safely (ratings may be Decimal)
        total = sum((float(r) for r in ratings))
        avg_rating = total / total_reviews

    acceptance_rate = await get_total_acceptance_rate(rider_profile)

    #print(f"Month of work: {month_of_work} | Earnings: {earnings} | Average Rating: {avg_rating} | Acceptance Rate: {acceptance_rate}")


    if month_of_work <= 2 and (earnings >= 16000 and earnings <= 18500):
        return {
            "tire": "Bronze",
            "status": "success",
        }
    elif month_of_work >= 2 and avg_rating >= 4.0 and (earnings >= 18500 and earnings <= 21000):
        return {
            "tire": "Silver",
            "status": "success",
        }
    elif month_of_work >= 2 and avg_rating >= 4.5 and acceptance_rate >= 90 and earnings >= 21000:
        return {
            "tire": "Gold",
            "status": "success",
        }
    else:
        return {
            "tire": "Not eligible",
            "status": "failed",
        }