import threading
import importlib
import pkgutil
import inspect
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import tasks

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def is_task(func):
    """Check if a function is a task (skip private/internal functions)"""
    return callable(func) and not func.__name__.startswith("_")

for loader, module_name, is_pkg in pkgutil.iter_modules(tasks.__path__):
    module = importlib.import_module(f"tasks.{module_name}")

    for name, func in inspect.getmembers(module, is_task):
        # Check if function has scheduling metadata
        schedule = getattr(func, "_schedule", None)
        if schedule:
            # If interval-based
            if "seconds" in schedule or "minutes" in schedule:
                scheduler.add_job(func, IntervalTrigger(**schedule), id=name)
            # If cron-based
            else:
                scheduler.add_job(func, CronTrigger(**schedule), id=name)
        else:
            # Default: run every minute for testing
            scheduler.add_job(func, IntervalTrigger(minutes=1), id=name)


def start_scheduler():
    scheduler.start()
    print("Scheduler started...")


threading.Thread(target=start_scheduler, daemon=True).start()
