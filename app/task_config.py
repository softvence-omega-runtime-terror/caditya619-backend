import importlib
import inspect
import pkgutil
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import tasks

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def is_task(func, module_name: str) -> bool:
    """
    Only schedule functions that are:
    - plain Python functions
    - defined in the current tasks module
    - explicitly decorated with @every(...)
    """
    return (
        inspect.isfunction(func)
        and func.__module__ == module_name
        and not func.__name__.startswith("_")
        and hasattr(func, "_schedule")
    )


def load_tasks():
    print("Scanning task modules...")
    for _, module_name, _ in pkgutil.iter_modules(tasks.__path__):
        print(f"Importing module: tasks.{module_name}")
        module = importlib.import_module(f"tasks.{module_name}")

        for name, func in inspect.getmembers(module):
            if not is_task(func, module.__name__):
                continue

            schedule = getattr(func, "_schedule", None)
            job_id = f"{module_name}_{name}"

            try:
                if "seconds" in schedule or "minutes" in schedule:
                    scheduler.add_job(func, IntervalTrigger(**schedule), id=job_id)
                else:
                    scheduler.add_job(func, CronTrigger(**schedule), id=job_id)

                print(f"Job added: {job_id} -> {schedule}")
            except Exception as e:
                print(f"Error scheduling {job_id}: {e}")


def start_scheduler():
    load_tasks()
    print("Starting APScheduler...")
    scheduler.start()
    print("Scheduler started and running...")


def start():
    threading.Thread(target=start_scheduler, daemon=True).start()
