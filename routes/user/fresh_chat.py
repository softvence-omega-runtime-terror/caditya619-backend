from fastapi import APIRouter, HTTPException, Depends
from tortoise.exceptions import DoesNotExist
from tortoise.contrib.pydantic import pydantic_model_creator

from applications.user.fresh_chat import FreshChat
from app.auth import login_required  # dependency to get current user

router = APIRouter(prefix="/freshchat", tags=["FreshChat"])

# Pydantic schemas
FreshChat_Pydantic = pydantic_model_creator(FreshChat, name="FreshChat")
FreshChatIn_Pydantic = pydantic_model_creator(FreshChat, name="FreshChatIn", exclude_readonly=True)

# -------------------------
# GET FreshChat for current user
# -------------------------
@router.get("/restore_id", response_model=FreshChat_Pydantic)
async def get_freshchat(current_user=Depends(login_required)):
    try:
        freshchat = await FreshChat.get(user_id=current_user.id)
        return await FreshChat_Pydantic.from_tortoise_orm(freshchat)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="FreshChat not found")

# -------------------------
# CREATE or UPDATE FreshChat for current user
# -------------------------
@router.post("/", response_model=FreshChat_Pydantic)
async def create_or_update_freshchat(
    freshchat_in: FreshChatIn_Pydantic,
    current_user=Depends(login_required)
):
    # Check if entry already exists
    existing = await FreshChat.filter(user_id=current_user.id).first()
    if existing:
        # Update existing record
        existing.restore_id = freshchat_in.restore_id
        await existing.save()
        return await FreshChat_Pydantic.from_tortoise_orm(existing)
    else:
        # Create new record
        freshchat_obj = await FreshChat.create(
            user_id=current_user.id,
            restore_id=freshchat_in.restore_id
        )
        return await FreshChat_Pydantic.from_tortoise_orm(freshchat_obj)
