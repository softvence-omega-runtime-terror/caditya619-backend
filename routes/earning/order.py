from fastapi import  APIRouter, Form, HTTPException, Depends

from app.auth import permission_required
from applications.customer.models import Order


router = APIRouter(prefix='/order', tags=['Order Management'])


@router.post("/manage-order-status", dependencies=[Depends(permission_required('update_order'))])
async def order_status_management(
    order_id: int = None,
    status: str = Form(None),
):
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if status not in ['delivered', 'shipped', 'processing', 'confirmed']:
        raise HTTPException(status_code=404, detail="Enter a valid status.")

    order.status = status
    await order.save(update_fields=["status"])

    return {
        "success": True,
        "message": "Order status updated successfully",
        "order_id": order.id,
        "status": order.status
    }