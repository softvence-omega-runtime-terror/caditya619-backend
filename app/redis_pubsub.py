import asyncio
import json
from redis.asyncio import Redis
from app.utils.websocket_manager import manager # Assuming 'manager' is accessible


async def start_redis_listener(redis: Redis):
    pubsub = redis.pubsub()
    await pubsub.psubscribe("msg:*")  # ← MUST BE "msg:*"

    print("Redis listener STARTED: msg:*")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        try:
            channel = message["channel"].decode()
            data = json.loads(message["data"])

            parts = channel.split(":", 2)
            if len(parts) != 3:
                continue
            _, to_type, to_id = parts

            print(f"Redis → {to_type}:{to_id}: {data['text']}")  # DEBUG
            await manager.send_to(data, to_type, to_id)

        except Exception as e:
            print(f"Redis listener error: {e}")