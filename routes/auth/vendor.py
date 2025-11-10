from fastapi import APIRouter, HTTPException, Form
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.token import  create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number

router = APIRouter(prefix='/vendor', tags=['Vendor Signup'])


@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(..., description="Enter a valid phone number +91XXXXXXXXXX"),
    name: str = Form(...),
    otp: str = Form(...),
    nid: str = Form(...),
    type: str = Form(..., description='food/groceries/medicine')
):
    phone = await phone_number(phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid phone number.")

    if not await verify_otp(phone, otp, purpose="vendor_signup"):
        raise HTTPException(status_code=400, detail="OTP not verified.")

    async with in_transaction() as connection:
        user = await User.get_or_none(phone=phone)
        
        if user and user.is_vendor:
                raise HTTPException(status_code=400, detail="Already registered as vendor.")

        if not user:
            user = await User.create(phone=phone, name=name, is_vendor=True, using_db=connection)
            await VendorProfile.get_or_create(
                user=user,
                defaults={
                    "type": type,
                    "nid": nid
                },
                using_db=connection,
            )

    token_data = {
        "sub": str(user.id),
        "is_active": user.is_active,
        "is_rider": user.is_rider,
        "is_vendor": user.is_vendor,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    roles = [
        role
        for role, active in {
            "superuser": user.is_superuser,
            "staff": user.is_staff,
            "vendor": user.is_vendor,
            "rider": user.is_rider,
        }.items()
        if active
    ]

    return {
        "message": "User created successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "roles": roles,
        "token_type": "bearer",
    }