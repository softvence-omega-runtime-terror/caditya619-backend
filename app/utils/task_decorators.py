# app/utils/task_decorators.py
def every(**kwargs):
    def decorator(func):
        func._schedule = kwargs  # attach schedule info
        return func
    return decorator
