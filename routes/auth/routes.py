from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from passlib.context import CryptContext
from applications.user.models import User
from applications.user.customer import CustomerProfile
from applications.user.vendor import VendorProfile
from applications.user.rider import RiderProfile
from app.token import get_current_user, create_access_token, create_refresh_token
from tortoise.contrib.pydantic import pydantic_model_creator
from app.utils.otp_manager import generate_otp, verify_otp
import re
from app.config import settings
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



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



@router.post("/send_otp/", description="""
### Test User Accounts:
- **Admin User** — `+919876543210` — Admin / Rider / Vendor / Staff / Superuser  
- **Rider One** — `+919876543211` — Rider  
- **Vendor One** — `+919876543212` — Vendor  
- **Mix One** — `+919876543213` — Rider / Vendor  
- **Staff One** — `+919876543214` — Staff  
- **Rider Two** — `+919876543215` — Rider  
- **Vendor Two** — `+919876543216` — Vendor  
- **Mix Two** — `+919876543217` — Rider / Vendor  
- **Staff Two** — `+919876543218` — Staff  
- **Test Ten** — `+919876543219` — Rider  
""")
async def send_otp(
        phone: str = Form('', description="Enter a valid phone number +91XXXXXXXXXX"),
        purpose: str = Form('signup', description="'login', 'rider_login', 'vendor_login', 'management_login', 'update_user_data', 'signup', 'rider_signup', 'vendor_signup'"),
):
    phone = await phone_number(phone)
    if not phone:
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
        elif purpose == 'rider_signup' and user and not user.is_rider:
            raise HTTPException(status_code=400, detail='You have already registered for rider.')
        elif purpose == 'vendor_signup' and user and user.is_vendor:
            raise HTTPException(status_code=400, detail='You have already registered for vendor.')
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
        "message": f"OTP sent to {phone}. Expires in 1 minute.{otp if settings.DEBUG else ""}",
        "purpose": purpose,
    }


@router.post("/login/", response_model=TokenResponse)
async def login(
        phone: str = Form('91', description="Enter a valid phone number +91XXXXXXXXXX"),
        otp: str = Form(''),
        purpose: str = Form('login', description="'login', 'rider_login', 'vendor_login', 'management_login', 'update_user_data'"),
):
    phone = await phone_number(phone)
    if phone:
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


# @router.post("/signup/", response_model=dict)
# async def signup(
#     phone: str = Form("91", description="Enter a valid phone number +91XXXXXXXXXX"),
#     name: str = Form(""),
#     otp: str = Form(""),
#     nid: Optional[str] = Form(""),
#     driving_license: Optional[str] = Form(""),
#     purpose: str = Form('signup', description="'signup', 'rider_signup', 'vendor_signup'"),
#     type: str = Form("", description='food/groceries/medicine')
# ):
#     # Validate phone
#     phone = await phone_number(phone)
#     if not phone:
#         raise HTTPException(status_code=400, detail="Enter a valid phone number.")

#     # Verify OTP
#     if not await verify_otp(phone, otp, purpose=purpose):
#         raise HTTPException(status_code=400, detail="OTP not verified.")

#     valid_purposes = ["signup", "rider_signup", "vendor_signup"]
#     if purpose not in valid_purposes:
#         raise HTTPException(status_code=400, detail="Invalid signup purpose.")

#     async with in_transaction() as connection:
#         user = await User.get_or_none(phone=phone)
        
#         # Already registered checks
#         if user:
#             if purpose == "signup":
#                 raise HTTPException(status_code=400, detail="Phone number already registered.")
#             elif purpose == "rider_signup" and user.is_rider:
#                 raise HTTPException(status_code=400, detail="Already registered as rider.")
#             elif purpose == "vendor_signup" and user.is_vendor:
#                 raise HTTPException(status_code=400, detail="Already registered as vendor.")

#         # Create user if not exists
#         if not user:
#             user = await User.create(phone=phone, name=name, using_db=connection)
#             await CustomerProfile.get_or_create(user=user, using_db=connection)

#         # Handle signup types
#         if purpose == "rider_signup":
#             if not (driving_license and nid):
#                 raise HTTPException(status_code=400, detail="Driving License and NID are required for rider signup.")
#             user.is_rider = True
#             await user.save(using_db=connection)
#             await RiderProfile.get_or_create(
#                 user=user,
#                 defaults={"driving_license": driving_license, "nid": nid},
#                 using_db=connection,
#             )

#         elif purpose == "vendor_signup":
#             if not nid:
#                 raise HTTPException(status_code=400, detail="NID is required for vendor signup.")
#             if not type:
#                 raise HTTPException(status_code=400, detail="Type is required for vendor signup.")
#             user.is_vendor = True
#             await user.save(using_db=connection)
#             await VendorProfile.get_or_create(
#                 user=user,
#                 type=type,
#                 defaults={"nid": nid},
#                 using_db=connection,
#             )

#     # Generate tokens
#     token_data = {
#         "sub": str(user.id),
#         "is_active": user.is_active,
#         "is_rider": user.is_rider,
#         "is_vendor": user.is_vendor,
#         "is_staff": user.is_staff,
#         "is_superuser": user.is_superuser,
#     }

#     access_token = create_access_token(token_data)
#     refresh_token = create_refresh_token(token_data)

#     roles = [
#         role
#         for role, active in {
#             "superuser": user.is_superuser,
#             "staff": user.is_staff,
#             "vendor": user.is_vendor,
#             "rider": user.is_rider,
#         }.items()
#         if active
#     ]

#     return {
#         "message": "User created successfully",
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "roles": roles,
#         "token_type": "bearer",
#     }

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


