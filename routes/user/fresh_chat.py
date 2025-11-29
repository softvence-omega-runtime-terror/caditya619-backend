from fastapi import APIRouter, HTTPException, Depends, Form
from tortoise.exceptions import DoesNotExist
from tortoise.contrib.pydantic import pydantic_model_creator

from applications.user.fresh_chat import FreshChat
from app.auth import login_required

router = APIRouter(prefix="/freshchat", tags=["FreshChat"])

# Pydantic schemas
FreshChat_Pydantic = pydantic_model_creator(FreshChat, name="FreshChat")
FreshChatIn_Pydantic = pydantic_model_creator(FreshChat, name="FreshChatIn", exclude_readonly=True)


@router.get("/restore_id", response_model=FreshChat_Pydantic)
async def get_freshchat(current_user=Depends(login_required)):
    try:
        freshchat = await FreshChat.get(user_id=current_user.id)
        return await FreshChat_Pydantic.from_tortoise_orm(freshchat)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="FreshChat not found")


@router.post("/", response_model=FreshChat_Pydantic)
async def create_or_update_freshchat(
    restore_id: str = Form(...),
    current_user=Depends(login_required)
):
    existing = await FreshChat.filter(user=current_user).first()
    if existing:
        existing.restore_id = restore_id
        await existing.save()
        return await FreshChat_Pydantic.from_tortoise_orm(existing)

    # Create new entry
    freshchat_obj = await FreshChat.create(
        user=current_user,
        restore_id=restore_id
    )
    return await FreshChat_Pydantic.from_tortoise_orm(freshchat_obj)
