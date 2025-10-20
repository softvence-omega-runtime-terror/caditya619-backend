from fastapi import HTTPException
import random
from app.redis import get_redis

OTP_EXPIRY_SECONDS = 60
MAX_ATTEMPTS_PER_HOUR = 10

def _otp_key(user_key: str, purpose: str):
    return f"{purpose}otp:{user_key}"

def _otp_attempts_key(user_key: str, purpose: str):
    return f"{purpose}otp_attempts:{user_key}"

async def generate_otp(user_key: str, purpose: str) -> str:
    redis = get_redis()
    otp_key = _otp_key(user_key, purpose)
    attempts_key = _otp_attempts_key(user_key, purpose)

    recent_count = await redis.get(attempts_key)
    recent_count = int(recent_count) if recent_count else 0
    if recent_count >= MAX_ATTEMPTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many OTP requests.")

    otp = str(random.randint(100000, 999999))
    await redis.set(otp_key, otp, ex=OTP_EXPIRY_SECONDS)

    attempts_count = await redis.incr(attempts_key)
    if attempts_count == 1:
        await redis.expire(attempts_key, 3600)

    print(f"📨 OTP for {user_key}: {otp}")
    return otp



async def verify_otp(user_key: str, otp_value: str, purpose: str) -> bool:
    redis = get_redis()
    otp_key = _otp_key(user_key, purpose)
    stored_otp = await redis.get(otp_key)

    if not stored_otp:
        raise HTTPException(status_code=400, detail="OTP expired or not found.")
    if stored_otp != otp_value:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    await redis.delete(otp_key)
    return True
