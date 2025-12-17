from fastapi import APIRouter, Depends, HTTPException, Request
from applications.user.models import User
from applications.user.rider import RiderProfile, Referral
from app.token import get_current_user
import random
import string
from datetime import datetime
from io import BytesIO
from PIL import Image
import qrcode
from starlette.responses import StreamingResponse
from .notifications import send_notification
from app.utils.translator import translate



from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider Referral'])





async def generate_code() -> str:
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    while await RiderProfile.filter(referral_code=code).exists():
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return code

@router.get("/referral/dashboard")
async def referral_dashboard(request:Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get(user=current_user)

    # Generate code if missing
    if not rider.referral_code:
        rider.referral_code = await generate_code()
        await rider.save()


    referrals = await Referral.filter(referrer=rider)
    active_count = len([r for r in referrals if r.status == "active"])

    return translate({
        "referral_code": rider.referral_code,
        "qr_data": rider.referral_code,  # Frontend makes QR from this
        "active_count": active_count,
        "pending_count": len(referrals) - active_count,
        "referrals": [
            {
                "name": (await r.referred.user).name if r.referred else "Pending",
                "status": r.status.title(),
                "earned": float(r.earned)
            }
            for r in referrals
        ]
    }, lang)

@router.get("/referral/qr")
async def referral_qr(current_user: User = Depends(get_current_user)):
    rider = await RiderProfile.get(user=current_user)
    if not rider.referral_code:
        rider.referral_code = await generate_code()
        await rider.save()

    # QR contains ONLY the code
    qr = qrcode.make(rider.referral_code)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")

@router.post("/referral/apply/{code}")
async def apply_referral(request:Request, code: str, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get(user=current_user)
    if rider.referral_code:
        raise HTTPException(400, translate("Already used a referral code", lang))

    referrer = await RiderProfile.get_or_none(referral_code=code.upper())
    if not referrer or referrer.id == rider.id:
        raise HTTPException(404, translate("Invalid referral code", lang))

    await Referral.create(
        referrer=referrer,
        code_used=code.upper(),
        status="pending"
    )
    return translate({"success": True, "message": "Referral applied!"}, lang)

# CALL THIS WHEN REFERRED RIDER COMPLETES FIRST RIDE
async def activate_referral(referred_rider_id: int):
    referral = await Referral.get_or_none(referred__id=referred_rider_id, status="pending")
    if not referral:
        return
    
    referrer = await RiderProfile.get(id=referral.referrer.id)
    if not referrer:
        raise HTTPException(404, "Referrer not found")

    referral.status = "active"
    referral.earned = 500
    referrer.current_balance += 500
    await referral.save()

    referrer = referral.referrer
    await referrer.save()

    try:
        await send_notification(
        {
            "title":"Referral Success!",
            "body":"You earned ₹500!",
            "rider_id":referrer.id
        }
        )
    except Exception as e:
        print(f"Failed to send referral notification: {e}")
    finally:
        pass