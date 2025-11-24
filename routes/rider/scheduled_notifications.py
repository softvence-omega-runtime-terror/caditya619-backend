# tasks/scheduled_notifications.py
from celery import Celery
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import asyncio
from app.utils.firebase_push import send_scheduled_push
from applications.user.rider import RiderProfile as Rider, WorkDay, Withdrawal
from .helper_functions import (
    get_deliveries_count, get_earnings, get_delivery_pay,
    get_weekly_bonuses, get_excellence_bonus, get_acceptance_rate, get_on_time_rate
)

app = Celery("rider_app")
app.conf.broker_url = "redis://localhost:6379/0"
app.conf.result_backend = "redis://localhost:6379/0"
app.conf.timezone = "Asia/Kolkata"

# DAILY 8:00 AM - Morning Motivation
@app.task
def daily_morning_push():
    today = datetime.utcnow().date()
    riders = asyncio.run(Rider.filter(is_online=True))
    
    for rider in riders:
        yesterday_earnings = asyncio.run(get_earnings(rider, today - timedelta(days=1), today))
        deliveries = asyncio.run(get_deliveries_count(rider, today - timedelta(days=1), today))
        
        if yesterday_earnings >= 1200:
            asyncio.run(send_scheduled_push(
                rider.id,
                "Great Day Yesterday!",
                f"You earned ₹{yesterday_earnings} with {deliveries} deliveries",
                {"type": "daily_summary"}
            ))
        else:
            asyncio.run(send_scheduled_push(
                rider.id,
                "Start Strong Today!",
                "Log in now — new orders waiting!",
                {"type": "morning_motivation"}
            ))

# SATURDAY 6:00 PM - Weekly Bonus Reminder
@app.task
def saturday_bonus_reminder():
    today = datetime.utcnow().date()
    if today.weekday() != 5:  # Not Saturday
        return
    
    riders = asyncio.run(Rider.all())
    week_start = today - timedelta(days=today.weekday())
    
    for rider in riders:
        work_days = asyncio.run(WorkDay.filter(rider=rider, date__gte=week_start).all())
        days_worked = len([wd for wd in work_days if not wd.is_scheduled_leave and wd.hours_worked >= 6])
        
        if days_worked == 5:
            asyncio.run(send_scheduled_push(
                rider.id,
                "Last Chance: ₹400 Weekly Bonus!",
                "Work tomorrow (Sunday) 6+ hours to earn ₹400 bonus!",
                {"type": "weekly_reminder", "bonus": "400"}
            ))

# MONTH END (28th) - Excellence Bonus Countdown
@app.task
def monthly_excellence_reminder():
    today = datetime.utcnow().date()
    if today.day not in [25, 27, 28]:
        return
        
    month_start = today.replace(day=1)
    riders = asyncio.run(Rider.all())
    
    for rider in riders:
        deliveries = asyncio.run(get_deliveries_count(rider, month_start, datetime.utcnow()))
        acceptance = asyncio.run(get_acceptance_rate(rider, month_start, datetime.utcnow()))
        on_time = asyncio.run(get_on_time_rate(rider, month_start, datetime.utcnow()))
        
        missing = []
        if deliveries < 170:
            missing.append(f"{170 - deliveries} deliveries")
        if acceptance < 90:
            missing.append("acceptance rate")
        if on_time < 92:
            missing.append("on-time rate")
            
        if missing and today.day == 28:
            asyncio.run(send_scheduled_push(
                rider.id,
                "Only 3 Days Left for ₹2000 Bonus!",
                f"Fix: {', '.join(missing)} to qualify!",
                {"type": "excellence_urgent"}
            ))

# WITHDRAWAL SUCCESS PUSH (after payout)
@app.task
def notify_withdrawal_success(withdrawal_id: int):
    withdrawal = asyncio.run(Withdrawal.get_or_none(id=withdrawal_id))
    if not withdrawal:
        return
        
    asyncio.run(send_scheduled_push(
        withdrawal.rider.id,
        "Withdrawal Successful!",
        f"₹{withdrawal.amount} sent to your bank account",
        {"type": "withdrawal_success", "amount": str(withdrawal.amount)}
    ))



