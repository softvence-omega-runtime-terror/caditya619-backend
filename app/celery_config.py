# celery_config.py
from celery import Celery
from celery.schedules import crontab

app = Celery("rider_app")
app.conf.broker_url = "redis://localhost:6379/0"
app.conf.result_backend = "redis://localhost:6379/0"
app.conf.timezone = "Asia/Kolkata"

beat_schedule = {
    "daily-morning-push": {
        "task": "tasks.scheduled_notifications.daily_morning_push",
        "schedule": crontab(hour=8, minute=0),
    },
    "saturday-bonus-reminder": {
        "task": "tasks.scheduled_notifications.saturday_bonus_reminder",
        "schedule": crontab(hour=18, minute=0, day_of_week=6),
    },
    "monthly-excellence-reminder": {
        "task": "tasks.scheduled_notifications.monthly_excellence_reminder",
        "schedule": crontab(hour=9, minute=0),
    },
}

app.conf.beat_schedule = beat_schedule
# Optional: remove redbeat if you don't have it installed
# app.conf.beat_scheduler = "redbeat.RedBeatScheduler"