import secrets

import httpx
from fastapi import HTTPException

from app.config import settings
from app.redis import get_redis


TWOFACTOR_BASE_URL = "https://2factor.in/API/V1"
OTP_EXPIRY_SECONDS = 120
MAX_ATTEMPTS_PER_HOUR = 30
TWOFACTOR_API_KEY = settings.TWOFACTOR_API_KEY
TWOFACTOR_OTP_TEMPLATE_NAME = settings.TWOFACTOR_OTP_TEMPLATE_NAME


def _otp_key(phone: str, purpose: str) -> str:
    return f"{purpose}otp:{phone}"


def _otp_attempts_key(phone: str, purpose: str) -> str:
    return f"{purpose}otp_attempts:{phone}"


async def _check_rate_limit(phone: str, purpose: str) -> str:
    redis = get_redis()
    attempts_key = _otp_attempts_key(phone, purpose)
    recent_count = await redis.get(attempts_key)
    recent_count = int(recent_count) if recent_count else 0
    if recent_count >= MAX_ATTEMPTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many OTP requests.")
    return attempts_key


async def _record_attempt(attempts_key: str) -> None:
    redis = get_redis()
    attempts_count = await redis.incr(attempts_key)
    if attempts_count == 1:
        await redis.expire(attempts_key, 3600)


async def generate_otp(phone: str, purpose: str) -> str:
    redis = get_redis()
    otp_key = _otp_key(phone, purpose)
    attempts_key = await _check_rate_limit(phone, purpose)
    otp = f"{secrets.randbelow(900000) + 100000}"

    if settings.DEBUG:
        await redis.set(otp_key, otp, ex=OTP_EXPIRY_SECONDS)
        await _record_attempt(attempts_key)
        print(f"OTP for {phone}: {otp}")
        return otp

    url = (
        f"{TWOFACTOR_BASE_URL}/{TWOFACTOR_API_KEY}/SMS/"
        f"{phone}/{otp}/{TWOFACTOR_OTP_TEMPLATE_NAME}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP. Please try again later.",
        ) from None

    if data.get("Status") != "Success":
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send OTP: {data.get('Details', 'Unknown error')}",
        )

    session_id = data.get("Details")
    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to send OTP: missing session id.")

    await redis.set(otp_key, session_id, ex=OTP_EXPIRY_SECONDS)
    await _record_attempt(attempts_key)
    return session_id


async def verify_otp(phone: str, otp_value: str, purpose: str) -> bool:
    redis = get_redis()
    otp_key = _otp_key(phone, purpose)
    attempts_key = _otp_attempts_key(phone, purpose)
    stored_value = await redis.get(otp_key)

    if not stored_value:
        raise HTTPException(status_code=400, detail="OTP expired or not found.")

    if settings.DEBUG:
        if stored_value != otp_value:
            raise HTTPException(status_code=400, detail="Invalid OTP.")
        await redis.delete(otp_key)
        await redis.delete(attempts_key)
        return True

    url = f"{TWOFACTOR_BASE_URL}/{TWOFACTOR_API_KEY}/SMS/VERIFY/{stored_value}/{otp_value}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=500,
            detail="Failed to verify OTP. Please try again later.",
        ) from None

    if data.get("Status") != "Success":
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    await redis.delete(otp_key)
    await redis.delete(attempts_key)
    return True
