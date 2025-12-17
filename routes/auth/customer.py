from fastapi import APIRouter, HTTPException, Form
from applications.user.models import User
from typing import Optional
from applications.user.customer import CustomerProfile
from app.token import  create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number

router = APIRouter(prefix='/customer', tags=['Customer Signup'])




@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(..., description="Enter a valid phone number +91XXXXXXXXXX"),
    name: Optional[str] = Form('Unknown User'),
    otp: str = Form(...),
):
    phone = await phone_number(phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid phone number.")

    if not await verify_otp(phone, otp, purpose="signup"):
        raise HTTPException(status_code=400, detail="OTP not verified.")


    async with in_transaction() as connection:
        user = await User.get_or_none(phone=phone)
        
        if user:
            raise HTTPException(status_code=400, detail="Phone number already registered.")

        if not user:
            user = await User.create(phone=phone, name=name, using_db=connection)
            await CustomerProfile.get_or_create(user=user, using_db=connection)


    # Generate tokens
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