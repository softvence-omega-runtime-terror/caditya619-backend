from fastapi import  APIRouter
from applications.customer.models import Order


router = APIRouter(prefix='/order', tags=['Order Management'])


@router.get("/manage")
async def order_management():
    return f"this is earning"