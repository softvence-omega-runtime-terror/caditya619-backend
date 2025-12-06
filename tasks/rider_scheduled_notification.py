from firebase_admin import messaging
from datetime import datetime, timedelta
import logging
import asyncio

from app.utils.task_decorators import every
from applications.user.rider import RiderProfile as Rider, WorkDay, Withdrawal, DeviceToken
from routes.rider.helper_functions import (
    get_deliveries_count, get_earnings, get_delivery_pay,
    get_weekly_bonuses, get_excellence_bonus, get_acceptance_rate, get_on_time_rate
)

logger = logging.getLogger(__name__)


# Helper function to send notification
async def send_push_notification(user_id: int, title: str, body: str, data: dict = None):
    """Send push notification using Firebase Admin SDK"""
    try:
        device = await DeviceToken.filter(user_id=user_id).first()
        if not device:
            logger.warning(f"No device token found for user {user_id}")
            return False

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=device.token,
        )

        response = messaging.send(message)
        logger.info(f"Notification sent to user {user_id}: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
        return False


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

# @every(seconds=5)
# def check_every_schedule():
#     """Runs every 5 seconds - Health check"""
#     print("Health Check")
#     logger.debug("Running every 5 seconds health check")


# DAILY 8:00 AM - Morning Motivation
@every(hour=8, minute=0)
def daily_morning_push():
    """Send morning motivation notifications to active riders"""
    async def _task():
        try:
            today = datetime.utcnow().date()
            yesterday_start = datetime.combine(today - timedelta(days=1), datetime.min.time())
            yesterday_end = datetime.combine(today, datetime.min.time())

            riders = await Rider.filter(is_online=True).all()

            for rider in riders:
                try:
                    yesterday_earnings = await get_earnings(rider, yesterday_start, yesterday_end)
                    deliveries = await get_deliveries_count(rider, yesterday_start, yesterday_end)

                    if yesterday_earnings >= 1200:
                        await send_push_notification(
                            rider.id,
                            "Great Day Yesterday!",
                            f"You earned ₹{yesterday_earnings} with {deliveries} deliveries",
                            {"type": "daily_summary", "earnings": str(yesterday_earnings)}
                        )
                    else:
                        await send_push_notification(
                            rider.id,
                            "Start Strong Today!",
                            "Log in now — new orders waiting!",
                            {"type": "morning_motivation"}
                        )
                except Exception as e:
                    logger.error(f"Error sending morning push to rider {rider.id}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in daily_morning_push: {str(e)}")

    try:
        asyncio.run(_task())
    except Exception as e:
        logger.error(f"Failed to execute daily_morning_push: {str(e)}")


# SATURDAY 6:00 PM - Weekly Bonus Reminder
@every(day_of_week=5, hour=18, minute=0)
def saturday_bonus_reminder():
    """Send weekly bonus reminder on Saturday evening"""
    async def _task():
        try:
            today = datetime.utcnow().date()
            if today.weekday() != 5:  # Not Saturday
                logger.info("Not Saturday, skipping weekly bonus reminder")
                return

            week_start = today - timedelta(days=today.weekday())
            riders = await Rider.all()

            for rider in riders:
                try:
                    work_days = await WorkDay.filter(
                        rider=rider,
                        date__gte=week_start,
                        date__lte=today
                    ).all()

                    days_worked = len([
                        wd for wd in work_days
                        if not wd.is_scheduled_leave and wd.hours_worked >= 6
                    ])

                    if days_worked == 5:
                        await send_push_notification(
                            rider.id,
                            "Last Chance: ₹400 Weekly Bonus!",
                            "Work tomorrow (Sunday) 6+ hours to earn ₹400 bonus!",
                            {"type": "weekly_reminder", "bonus": "400", "days_worked": str(days_worked)}
                        )
                except Exception as e:
                    logger.error(f"Error sending weekly reminder to rider {rider.id}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in saturday_bonus_reminder: {str(e)}")

    try:
        asyncio.run(_task())
    except Exception as e:
        logger.error(f"Failed to execute saturday_bonus_reminder: {str(e)}")


# MONTH END (25th, 27th, 28th) - Excellence Bonus Countdown
@every(day=25, hour=9, minute=0)
def monthly_excellence_reminder():
    """Send excellence bonus reminder near month end"""
    async def _task():
        try:
            today = datetime.utcnow().date()
            if today.day not in [25, 27, 28]:
                logger.info(f"Day {today.day} - skipping excellence reminder")
                return

            month_start = datetime.combine(today.replace(day=1), datetime.min.time())
            now = datetime.utcnow()
            riders = await Rider.all()

            for rider in riders:
                try:
                    deliveries = await get_deliveries_count(rider, month_start, now)
                    acceptance = await get_acceptance_rate(rider, month_start, now)
                    on_time = await get_on_time_rate(rider, month_start, now)

                    missing = []

                    if deliveries < 170:
                        missing.append(f"{170 - deliveries} deliveries")
                    if acceptance < 90:
                        missing.append("acceptance rate")
                    if on_time < 92:
                        missing.append("on-time rate")

                    if missing:
                        days_left = (today.replace(day=28) - today).days + 1 if today.day <= 28 else 0

                        if today.day == 28:
                            await send_push_notification(
                                rider.id,
                                "Last Day for ₹2000 Bonus!",
                                f"Fix: {', '.join(missing)} to qualify!",
                                {"type": "excellence_urgent", "missing": ", ".join(missing)}
                            )
                        else:
                            await send_push_notification(
                                rider.id,
                                f"{days_left} Days Left for ₹2000 Bonus!",
                                f"Improve: {', '.join(missing)}",
                                {"type": "excellence_reminder", "missing": ", ".join(missing)}
                            )
                except Exception as e:
                    logger.error(f"Error sending excellence reminder to rider {rider.id}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in monthly_excellence_reminder: {str(e)}")

    try:
        asyncio.run(_task())
    except Exception as e:
        logger.error(f"Failed to execute monthly_excellence_reminder: {str(e)}")


# ============================================================================
# EVENT-BASED NOTIFICATIONS (Call these from relevant logic)
# ============================================================================

def notify_withdrawal_success(withdrawal_id: int):
    """Send notification when withdrawal is successful"""
    async def _task():
        try:
            withdrawal = await Withdrawal.get_or_none(id=withdrawal_id).prefetch_related('rider')
            if not withdrawal:
                logger.warning(f"Withdrawal {withdrawal_id} not found")
                return

            await send_push_notification(
                withdrawal.rider.id,
                "Withdrawal Successful!",
                f"₹{withdrawal.amount} sent to your bank account",
                {
                    "type": "withdrawal_success",
                    "amount": str(withdrawal.amount),
                    "withdrawal_id": str(withdrawal_id)
                }
            )
        except Exception as e:
            logger.error(f"Error in notify_withdrawal_success: {str(e)}")

    try:
        asyncio.run(_task())
    except Exception as e:
        logger.error(f"Failed to execute notify_withdrawal_success: {str(e)}")


def notify_order_assigned(rider_id: int, order_id: int, pickup_location: str):
    """Send notification when new order is assigned"""
    async def _task():
        try:
            await send_push_notification(
                rider_id,
                "New Order Assigned!",
                f"Pickup from {pickup_location}",
                {
                    "type": "order_assigned",
                    "order_id": str(order_id),
                    "pickup": pickup_location
                }
            )
        except Exception as e:
            logger.error(f"Error in notify_order_assigned: {str(e)}")

    try:
        asyncio.run(_task())
    except Exception as e:
        logger.error(f"Failed to execute notify_order_assigned: {str(e)}")