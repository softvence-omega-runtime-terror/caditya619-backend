from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from pydantic import BaseModel
from pydantic import EmailStr
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from applications.user.models import User
from app.token import get_current_user, create_access_token, create_refresh_token, SECRET_KEY, ALGORITHM, REFRESH_SECRET_KEY
from tortoise.contrib.pydantic import pydantic_model_creator
from app.utils.otp_manager import generate_otp, verify_otp
import re
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def detect_input_type(value: str) -> str:
    value = value.strip()

    email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    phone_regex = r'^(\+?\d{1,4}[\s-]?)?\d{10,14}$'

    if re.match(email_regex, value):
        return 'email'
    elif re.match(phone_regex, value):
        return 'phone'
    else:
        return 'username'


class OAuth2EmailPasswordForm:
    def __init__(
        self,
        email: EmailStr = Form(...),
        password: str = Form(...),
        scope: str = Form(""),
        client_id: str = Form(None),
        client_secret: str = Form(None),
    ):
        self.email = email
        self.password = password
        self.scopes = scope.split()
        self.client_id = client_id
        self.client_secret = client_secret


User_Pydantic = pydantic_model_creator(User, name="User")
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


@router.post("/login_auth2/", response_model=TokenResponse)
async def login_auth2(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await User.get_or_none(email=form_data.username)  # <- use username as email
    if not user or not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": str(user.id),
        "username": user.username,
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



@router.post("/login/", response_model=TokenResponse)
async def login(
    user_key: str = Form(...),
    password: str = Form(...)
):
    lookup_field = await detect_input_type(user_key)
    
    if lookup_field == "email":
        user = await User.get_or_none(email=user_key)
    elif lookup_field == "phone":
        user = await User.get_or_none(phone=user_key)
    else:
        user = await User.get_or_none(username=user_key)


    if not user or not pwd_context.verify(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }



@router.post("/signup/", response_model=dict)
async def signup(
    user_key: str = Form(...),
    password: str = Form(...),
    otp: str = Form(...),
):
    await verify_otp(user_key, otp, purpose="signup")

    lookup_field = await detect_input_type(user_key)
    if lookup_field not in ["email", "phone"]:
        raise HTTPException(status_code=400, detail=f"{lookup_field.capitalize()} is not valid")

    existing_user = await User.get_or_none(**{lookup_field: user_key})
    if existing_user:
        raise HTTPException(status_code=400, detail=f"{lookup_field.capitalize()} already registered")

    hashed_password = pwd_context.hash(password)
    user = await User.create(**{lookup_field: user_key}, password=hashed_password)

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "message": "User created successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }



@router.post("/reset_password/", response_model=dict)
async def reset_password(
    user: User = Depends(get_current_user),
    password: str = Form(...)
):
    user.password = pwd_context.hash(password)
    await user.save()

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "message": "Password reset successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }



@router.post("/forgot_password/", response_model=dict)
async def forgot_password(
    user_key: str = Form(...),
    password: str = Form(...),
    otp: str = Form(...),
):
    await verify_otp(user_key, otp, purpose="forgot_password")

    lookup_field = await detect_input_type(user_key)
    if lookup_field == "email":
        user = await User.get_or_none(email=user_key)
    elif lookup_field == "phone":
        user = await User.get_or_none(phone=user_key)
    else:
        user = await User.get_or_none(username=user_key)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = pwd_context.hash(password)
    await user.save()

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "message": "Password reset successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }





@router.get("/verify-token/")
async def verify_token(request: Request, user: User = Depends(get_current_user)):
    response_data = {
        "status": "success",
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    if hasattr(request.state, "new_tokens"):
        response_data["new_tokens"] = request.state.new_tokens

    return response_data



@router.post("/send_otp/")
async def send_otp(
    user_key: str = Form(...),
    purpose: str = Form(...),
):
    key_type = await detect_input_type(user_key)
    if key_type == "email":
        user = await User.get_or_none(email=user_key)
    elif key_type == "phone":
        user = await User.get_or_none(phone=user_key)
    else:
        user = await User.get_or_none(username=user_key)
        
    if purpose == "forgot_password":
        if not user:
            raise HTTPException(status_code=400, detail="User not found for password reset.")
    elif purpose == "signup":
        if user:
            raise HTTPException(status_code=400, detail=f"{key_type} already registered.")
    else:
        raise HTTPException(status_code=400, detail="Invalid purpose.")
    
    try:
        otp = await generate_otp(user_key, purpose)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate OTP")

    return {
        "status": "success",
        "message": f"OTP sent to {user_key}. Expires in 1 minute.",
        "purpose": purpose,
    }



@router.post("/verify_otp/")
async def verify_otp_route(
    user_key: str = Form(...),
    otpValue: str = Form(...),
    purpose: str = Form(...),
):
    try:
        await verify_otp(user_key, otpValue, purpose)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "message": "OTP verified successfully."
    }