from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time
from tortoise import fields, models
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile as Rider, Withdrawal, Notification, RiderReview, RiderFeesAndBonuses
from app.utils.file_manager import save_file, update_file, delete_file
from .helper_functions import *
from applications.customer.models import Order
from tortoise.functions import Avg, Sum





from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider State'])




# Wallet
@router.get("/wallet/")
async def get_wallet(period: str = "month", user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    rider = await Rider.get(user=user)
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    feesandbonus = await RiderFeesAndBonuses.get(id=1)
    if not feesandbonus:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fees and bonuses not found")
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        deliveries = await get_deliveries_count(rider, start, end)
        earnings = await get_earnings(rider, start, end)
        return {"deliveries": deliveries, "earnings": earnings}

    elif period == "week":
        week_start_date = now.date() - timedelta(days=now.weekday())
        start = datetime.combine(week_start_date, datetime.min.time())
        end = now + timedelta(days=1)
        deliveries = await get_deliveries_count(rider, start, end)
        delivery_pay = await get_delivery_pay(rider, start, end)
        # Weekly bonus status
        dates = [(week_start_date + timedelta(days=d)) for d in range((now.date() - week_start_date).days + 1)]
        work_days = await WorkDay.filter(rider=rider, date__in=dates).all()
        work_days_dict = {wd.date: wd for wd in work_days}
        days_worked = 0
        all_hours_ok = True
        all_orders_ok = True
        for d in dates:
            wd = work_days_dict.get(d)
            if wd:
                days_worked += 1 if not wd.is_scheduled_leave else 0
                if not wd.is_scheduled_leave:
                    if wd.hours_worked < 6:
                        all_hours_ok = False
                    if wd.order_offer_count < 1:
                        all_orders_ok = False
        total_days = 6  # Monday-Saturday
        remaining_days = total_days - len(dates)
        status = "In Progress" if now.date().weekday() < 5 else "Qualified" if len(work_days) == total_days and all_hours_ok and all_orders_ok else "Not Qualified"
        if status == "Qualified":
            bonus = feesandbonus.weekly_bonus
        else:
            bonus = 0
        current_total = delivery_pay
        projected = current_total + bonus
        return {
            "deliveries": deliveries,
            "delivery_pay": delivery_pay,
            "bonus_status": status,
            "days_worked": days_worked,
            "remaining_days": remaining_days,
            "total_rorking_day": 6,
            "hours_ok": all_hours_ok,
            "orders_ok": all_orders_ok,
            "current_total": current_total,
            "projected_total": projected
        }

    elif period == "month":
        month_start_date = now.date().replace(day=1)
        month_start = datetime.combine(month_start_date, datetime.min.time())
        month_end = month_start + relativedelta(months=1)
        deliveries = await get_deliveries_count(rider, month_start, month_end)
        delivery_pay = await get_delivery_pay(rider, month_start, month_end)      
        weekly_bonuses_dict = await get_weekly_bonuses(rider, month_start_date, (month_end - timedelta(seconds=1)).date())
        weekly_bonuses = weekly_bonuses_dict["total"]
        excellence_bonus = await get_excellence_bonus(rider, month_start, month_end)
        subtotal = to_float(delivery_pay) + to_float(weekly_bonuses) + to_float(excellence_bonus)
        guarantee = feesandbonus.rider_base_salary
        top_up = max(to_float(guarantee) - subtotal, 0)
        final_earnings = subtotal + top_up

        # Bonus status
        rated_count = await get_monthly_rated_count(rider, month_start, month_end)
        rating = await get_monthly_rating(rider, month_start, month_end)
        acceptance = await get_acceptance_rate(rider, month_start, month_end)
        on_time = await get_on_time_rate(rider, month_start, month_end)
        complaints = await get_serious_complaints(rider, month_start, month_end)
        bonus_status = {
            "deliveries": f"{deliveries}/170 {True if deliveries >= 170 else False}",
            "rating": f"{rating:.1f}/4.0 {True if rating >= 4.0 or rated_count < 20 else False}",
            "acceptance": f"{acceptance:.0f}%/90% {True if acceptance >= 90 else False}",
            "on_time": f"{on_time:.0f}%/92% {True if on_time >= 92 else False}",
            "complaints": f"{complaints} {True if complaints == 0 else False}",
            "criteria_met": sum([deliveries >= 170, rating >= 4.0 or rated_count < 20, acceptance >= 90, on_time >= 92, complaints == 0])
        }

        # Forecast
        target = 14000
        percentage = (subtotal / target) * 100
        remaining_deliveries = max((target - subtotal) / 44, 0)

        return {
            "deliveries": deliveries,
            "delivery_pay": delivery_pay,
            "weekly_bonuses": weekly_bonuses,
            "weekly_statuses": weekly_bonuses_dict["statuses"],
            "excellence_bonus": excellence_bonus,
            "subtotal": subtotal,
            "top_up": top_up,
            "final_earnings": final_earnings,
            "bonus_status": bonus_status,
            "forecast": {
                "current": subtotal,
                "target": target,
                "percentage": percentage,
                "remaining_deliveries": remaining_deliveries
            }
        }

    elif period == "year":
        year_start_date = now.date().replace(month=1, day=1)
        year_start = datetime.combine(year_start_date, datetime.min.time())
        year_end = year_start + relativedelta(years=1)
        total_deliveries = await get_deliveries_count(rider, year_start, year_end)
        monthly_breakdown = {}
        total_earnings = 0
        best_month = None
        best_amount = 0
        for m in range(1, now.month + 1):
            m_start = year_start + relativedelta(months=m-1)
            m_end = m_start + relativedelta(months=1)
            # Calculate final_earnings for each month
            delivery_pay = await get_delivery_pay(rider, m_start, m_end)
            weekly_bonuses_dict = await get_weekly_bonuses(rider, m_start.date(), (m_end - timedelta(seconds=1)).date())
            weekly_bonuses = weekly_bonuses_dict["total"]
            excellence_bonus = await get_excellence_bonus(rider, m_start, m_end)
            subtotal = to_float(delivery_pay) + to_float(weekly_bonuses) + to_float(excellence_bonus)
            top_up = max(8000 - subtotal, 0)
            earnings = subtotal + top_up
            month_name = m_start.strftime("%B")
            monthly_breakdown[month_name] = earnings
            total_earnings += earnings
            if earnings > best_amount:
                best_amount = earnings
                best_month = month_name
        average_monthly = total_earnings / now.month if now.month > 0 else 0
        return {
            "total_deliveries": total_deliveries,
            "total_earnings": total_earnings,
            "monthly_breakdown": monthly_breakdown,
            "average_monthly": average_monthly,
            "best_month": best_month
        }
    else:
        raise HTTPException(400, "Invalid period")
    

@router.get("/current_balance/")
async def get_current_balance(user: User = Depends(get_current_user)):
    rider = await Rider.get(user=user)
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    return {"current_balance": rider.current_balance}


# Withdrawal
@router.post("/wallet/withdraw/")
async def withdraw(amount: float, user: User = Depends(get_current_user)):
    rider = await Rider.get(user=user)
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    if amount > rider.current_balance or amount <= 0:
        raise HTTPException(400, "Invalid amount")
    withdrawal = Withdrawal(rider=rider, amount=amount)
    await withdrawal.save()
    rider.current_balance -= amount
    await rider.save()
    return {"status": "pending", "amount": amount}

# Notifications
@router.get("/notifications/", response_model=List[NotificationOut])
async def get_notifications(rider: rider = Depends(get_current_user)):
    notifs = await Notification.filter(rider=rider).order_by("-created_at").all()
    return [NotificationOut(**n.__dict__) for n in notifs]

# Performance
@router.get("/performance/")
async def get_performance(rider: rider = Depends(get_current_user)):
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    deliveries = await get_deliveries_count(rider, month_start, now + timedelta(days=1))
    # rating = await get_monthly_rating(rider, month_start, now + timedelta(days=1))
    acceptance = await get_acceptance_rate(rider, month_start, now + timedelta(days=1))
    on_time = await get_on_time_rate(rider, month_start, now + timedelta(days=1))
    return {
        "total_deliveries": deliveries,
        # "customer_rating": f"{rating:.1f}/5.0",
        "acceptance_rate": f"{acceptance:.0f}%",
        "on_time_rate": f"{on_time:.0f}%"
    }

@router.get("/leaderboard/")
async def get_leaderboard(user: User = Depends(get_current_user)):
    rider = await Rider.get(user=user)
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = month_start + relativedelta(months=1)
    all_riders = await Rider.all()
    scores = []
    for p in all_riders:
        deliveries = await get_deliveries_count(p, month_start, month_end)
        rating = 0            #await get_monthly_rating(p, month_start, month_end)
        on_time = await get_on_time_rate(p, month_start, month_end)
        score = (deliveries * 0.5) + (rating * 50) + (on_time * 2)
        scores.append((p.id, score, deliveries, rating, on_time))
    scores.sort(key=lambda x: x[1], reverse=True)
    rank = next((i+1 for i, s in enumerate(scores) if s[0] == rider.id), None)
    total_riders = len(scores)
    my_score, my_deliveries, my_rating, my_on_time = next((s for s in scores if s[0] == rider.id), (0,0,0,0))[1:]
    prize_structure = {1: 2000, 2: 1000, 3: 500}
    prize = prize_structure.get(rank, 250 if rank <= 10 else 0)
    return {
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
    }





@router.get("/rider/rider-ratings/")
async def get_rider_ratings(current_user: User = Depends(get_current_user)):
    # FIX 1: Correct model name
    rider_profile = await Rider.get_or_none(user=current_user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider not found")

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

    return {
        "rider_id": rider_profile.id,
        "avg_rating": round(float(avg_rating), 2),
        "total_reviews": total_reviews,
        "status": "success",
    }
