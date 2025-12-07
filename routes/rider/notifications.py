from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from applications.user.rider import DeviceToken
from firebase_admin import messaging
from applications.user.models import User
from app.utils.firebase_push import cred
from app.token import get_current_user

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Notifications'])

class DeviceTokenIn(BaseModel):
    user_id: int
    token: str
    platform: str

@router.post("/save_token/")
async def save_device_token(data: DeviceTokenIn, user: User = Depends(get_current_user)):
    exists = await DeviceToken.filter(user_id=user.id, platform=data.platform).first()
    if exists:
        exists.token = data.token
        await exists.save()
    else:
        await DeviceToken.create(**data.dict())
    return {"status": "success"}





class NotificationIn(BaseModel):
    user_id: int
    title: str
    body: str

@router.post("/send_notification/")
async def send_notification(data: NotificationIn):
    device = await DeviceToken.filter(user_id=data.user_id).first()
    if not device:
        raise HTTPException(404, "Device token not found")
    message = messaging.Message(
        notification=messaging.Notification(
            title=data.title,
            body=data.body,
        ),
        token=device.token,
    )
    try:
        resp = messaging.send(message)
        return {"status": "sent", "response": resp}
    except Exception as e:
        raise HTTPException(500, f"Send error: {e}")







@router.get("/test_notification/")
async def test(user: User = Depends(get_current_user)):
   deliveries = 42  # Example metrics or calculations

   await send_notification(NotificationIn(
        user_id=user.id,
        title="Performance Update",
        body=f"You delivered {deliveries} orders this month!"
    ))