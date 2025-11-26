# tasks/my_tasks.py
from app.utils.task_decorators import every

# @every(seconds=1)
# def check_every_5sec():
#     print("Running every 1 seconds")
#
# @every(hour=8, minute=0)
# def daily_morning_push():
#     print("Running daily morning push")
#
# @every(day_of_week=6, hour=18, minute=0)
# def saturday_bonus_reminder():
#     print("Running Saturday bonus reminder")
#
# @every(day=1, hour=9, minute=0)
# def monthly_excellence_reminder():
#     print("Running monthly excellence reminder")


@every(seconds=5)
def check_every():
    print("Running every 5 seconds")