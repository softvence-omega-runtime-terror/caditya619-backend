from redis.asyncio import Redis
redis_client: Redis | None = None

def init_redis(url="redis://localhost:6379/0"):
    global redis_client
    if not redis_client:
        redis_client = Redis.from_url(url, encoding="utf-8", decode_responses=True)
    return redis_client

def get_redis() -> Redis:
    if not redis_client:
        raise RuntimeError("Redis not initialized")
    return redis_client
