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

# @every(day_of_week='mon', hour=10, minute=0)
# def weekly_task():
#     print("Runs every Monday at 10:00 AM")

@every(seconds=5)
def check_every_schedule():
    print("Running every 5 seconds")


@every(seconds=1)
def check_every_schedule1sec():
    print("Running every 1 seconds")

@every(seconds=2)
def check_every_schedule2sec():
    print("Running every 2 seconds")

@every(seconds=3)
def check_every_schedule3sec():
    print("Running every 3 seconds")

@every(seconds=4)
def check_every_schedule4sec():
    print("Running every 4 seconds")