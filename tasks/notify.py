from app.utils.task_decorators import every

@every(minutes=10)
def check_every_in_10minute():
    print("Running every 10 seconds")
