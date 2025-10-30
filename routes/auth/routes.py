from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from passlib.context import CryptContext
from applications.user.models import User, CustomerProfile, VendorProfile, RiderProfile
from app.token import get_current_user, create_access_token, create_refresh_token
from tortoise.contrib.pydantic import pydantic_model_creator
from app.utils.otp_manager import generate_otp, verify_otp
import re
from app.config import settings

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



# (?:\+91[\s-]?|0)? → optional country code +91, or a leading 0.
# [6-9] → Indian mobile numbers always start with 6, 7, 8, or 9.
# \d{9} → remaining 9 digits (total 10 digits).
# So it matches:
# 9876543210
# 09876543210
# +919876543210
# +91 9876543210
# +91-9876543210


async def detect_input_type(value: str) -> str:
    value = value.strip()
    email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    phone_regex = r'^(?:\+91|0)?[6-9]\d{9}$'

    if re.match(email_regex, value):
        return 'email'
    elif re.match(phone_regex, value):
        return 'phone'
    else:
        raise ValueError('Please enter a correct phone number.')


class OAuth2EmailPasswordForm:
    def __init__(
            self,
            phone: str = Form(...),
            otp: str = Form(...),
            scope: str = Form(""),
            client_id: str = Form(None),
            client_secret: str = Form(None),
    ):
        self.phone = phone
        self.scopes = scope.split()
        self.client_id = client_id
        self.client_secret = client_secret


User_Pydantic = pydantic_model_creator(User, name="User")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


@router.post("/login_auth2/", response_model=TokenResponse)
async def login_auth2(form_data: OAuth2EmailPasswordForm = Depends()):
    user = await User.get_or_none(phone=form_data.phone)
    # if not user or not pwd_context.verify(form_data.password, user.password):
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid email or password",
    #         headers={"WWW-Authenticate": "Bearer"},
    #     )

    token_data = {
        "sub": str(user.id),
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }



@router.post("/send_otp/")
async def send_otp(
        phone: str = Form(...),
        purpose: str = Form(...),
):
    lookup_field = await detect_input_type(phone)
    if not lookup_field == "phone":
        raise HTTPException(status_code=400, detail="Enter correct phone number.")

    user = await User.get_or_none(phone=phone)

    if purpose in ['login', 'rider_login', 'vendor_login', 'management_login', 'update_user_data']:
        if not user:
            raise HTTPException(status_code=400, detail="User not found.")
        elif purpose == 'rider_login' and not user.is_rider:
            raise HTTPException(status_code=400, detail='You are not yet registered for rider.')
        elif purpose == 'vendor_login' and not user.is_vendor:
            raise HTTPException(status_code=400, detail='You are not yet registered for vendor.')
        elif purpose == 'management_login' and not (user.is_superuser or user.is_staff):
            raise HTTPException(status_code=400, detail='Invalid credentials.')
    elif purpose in ['signup', 'rider_signup', 'vendor_signup']:
        if purpose == 'signup' and user:
            raise HTTPException(status_code=400, detail=f"{phone} already registered.")
        elif purpose == 'rider_signup' and user.is_rider:
            raise HTTPException(status_code=400, detail='You are not yet registered for rider.')
        elif purpose == 'vendor_signup' and not user.is_vendor:
            raise HTTPException(status_code=400, detail='You are not yet registered for vendor.')
    else:
        raise HTTPException(status_code=400, detail="Invalid purpose.")

    try:
        otp = await generate_otp(phone, purpose)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate OTP")

    return {
        "status": "success",
        "message": f"OTP sent to {phone}. Expires in 1 minute.{otp}",
        "purpose": purpose,
    }


@router.post("/login/", response_model=TokenResponse)
async def login(
        phone: str = Form(...),
        otp: str = Form(...),
        purpose: str = Form(...),
):
    lookup_field = await detect_input_type(phone)
    if lookup_field == "phone":
        user = await User.get_or_none(phone=phone)
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
    else:
        raise HTTPException(status_code=400, detail='Please enter your registered phone no.')

    verified = await verify_otp(phone, otp, purpose=purpose)

    if not user or not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )


    token_data = {
        "sub": str(user.id),
        "is_active": user.is_active,
        "is_rider": user.is_rider,
        "is_vendor": user.is_vendor,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    roles = []
    if user.is_superuser:
        roles.append("superuser")
    if user.is_staff:
        roles.append("staff")
    if user.is_vendor:
        roles.append("vendor")
    if user.is_rider:
        roles.append("rider")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "roles": roles,
        "token_type": "bearer",
    }


@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(...),
    name: str = Form(...),
    otp: str = Form(...),
    nid: Optional[str] = Form(None),
    driving_license: Optional[str] = Form(None),
    purpose: str = Form(...)
):
    if await detect_input_type(phone) != "phone":
        raise HTTPException(status_code=400, detail="Enter a valid phone number.")

    verified = await verify_otp(phone, otp, purpose=purpose)
    if not verified:
        raise HTTPException(status_code=400, detail="OTP not verified.")

    valid_purposes = ["signup", "rider_signup", "vendor_signup"]
    if purpose not in valid_purposes:
        raise HTTPException(status_code=400, detail="Invalid signup purpose.")

    user = await User.get_or_none(phone=phone)

    if not user:
        user = await User.create(phone=phone, name=name)
        await CustomerProfile.get_or_create(user=user)

    if purpose == "signup":
        await CustomerProfile.get_or_create(user=user)
        if user.is_rider or user.is_vendor:
            raise HTTPException(
                status_code=400, detail="Already registered as rider or vendor."
            )

    elif purpose == "rider_signup":
        if user.is_rider:
            raise HTTPException(status_code=400, detail="Already registered as rider.")
        if not (driving_license and nid):
            raise HTTPException(
                status_code=400,
                detail="Driving License and NID are required for rider signup.",
            )

        user.is_rider = True
        await user.save()
        await RiderProfile.get_or_create(
            user=user,
            defaults={"driving_license": driving_license, "nid": nid},
        )

    elif purpose == "vendor_signup":
        if user.is_vendor:
            raise HTTPException(status_code=400, detail="Already registered as vendor.")
        if not nid:
            raise HTTPException(
                status_code=400, detail="NID is required for vendor signup."
            )

        user.is_vendor = True
        await user.save()
        await VendorProfile.get_or_create(
            user=user,
            defaults={"nid": nid},
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




@router.get("/verify-token/")
async def verify_token(request: Request, user: User = Depends(get_current_user)):
    response_data = {
        "status": "success",
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_rider": user.is_rider,
        "is_vendor": user.is_vendor,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    if hasattr(request.state, "new_tokens"):
        response_data["new_tokens"] = request.state.new_tokens

    return response_data


