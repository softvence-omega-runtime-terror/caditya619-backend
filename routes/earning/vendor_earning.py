from fastapi import  APIRouter
router = APIRouter(prefix='vendor', tags=['Vendor Earning'])


@router.get("/monthly")
async def monthly():
    return f"this is earning"