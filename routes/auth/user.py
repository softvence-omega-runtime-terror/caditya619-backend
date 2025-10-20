from fastapi import APIRouter
router = APIRouter(tags=["Auth"])

@router.get("/user/me")
async def read_user_me():
    return {"user_id": "the_current_user"}