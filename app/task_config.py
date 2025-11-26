import importlib
import pkgutil
import inspect
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import tasks

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def is_task(func):
    return callable(func) and not func.__name__.startswith("_")

def load_tasks():
    print("🔍 Scanning task modules...")
    for loader, module_name, is_pkg in pkgutil.iter_modules(tasks.__path__):
        print(f"📦 Importing module: tasks.{module_name}")
        module = importlib.import_module(f"tasks.{module_name}")

        for name, func in inspect.getmembers(module, is_task):
            schedule = getattr(func, "_schedule", None)
            job_id = f"{module_name}_{name}"  # unique job ID

            try:
                if schedule:
                    if "seconds" in schedule or "minutes" in schedule:
                        scheduler.add_job(func, IntervalTrigger(**schedule), id=job_id)
                    else:
                        scheduler.add_job(func, CronTrigger(**schedule), id=job_id)
                else:
                    scheduler.add_job(func, IntervalTrigger(minutes=1), id=job_id)

                print(f"   ✔ Job added: {job_id} -> {schedule}")
            except Exception as e:
                print(f"   ❌ Error scheduling {job_id}: {e}")

def start_scheduler():
    load_tasks()
    print("🚀 Starting APScheduler...")
    scheduler.start()
    print("✅ Scheduler started and running...")

def start():
    threading.Thread(target=start_scheduler, daemon=True).start()


#
# from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.triggers.interval import IntervalTrigger
# from apscheduler.triggers.cron import CronTrigger
# import time
# from tasks.schedule_notify import (
#     check_every_5sec,
#     daily_morning_push,
#     saturday_bonus_reminder,
#     monthly_excellence_reminder
# )
#
# def start_scheduler():
#     scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
#
#     # Every 5 seconds
#     scheduler.add_job(check_every_5sec, IntervalTrigger(seconds=5), id="check_every_5sec")
#
#     # Daily at 8:00 AM
#     scheduler.add_job(daily_morning_push, CronTrigger(hour=8, minute=0), id="daily_morning_push")
#
#     # Saturday at 6:00 PM
#     scheduler.add_job(saturday_bonus_reminder, CronTrigger(day_of_week=6, hour=18, minute=0), id="saturday_bonus_reminder")
#
#     # 1st day of the month at 9:00 AM
#     scheduler.add_job(monthly_excellence_reminder, CronTrigger(day=1, hour=9, minute=0), id="monthly_excellence_reminder")
#
#     scheduler.start()
#     print("Scheduler started...")
#
#     try:
#         while True:
#             time.sleep(1)
#     except (KeyboardInterrupt, SystemExit):
#         scheduler.shutdown()
#         print("Scheduler stopped.")
#
# if __name__ == "__main__":
#     start_scheduler()
