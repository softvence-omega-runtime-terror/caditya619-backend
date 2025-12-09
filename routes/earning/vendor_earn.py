from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from tortoise.transactions import in_transaction
from decimal import Decimal, ROUND_DOWN
from applications.user.models import User
from datetime import datetime, timedelta
import uuid
from app.auth import vendor_required
import inspect
import asyncio

from applications.user.vendor import VendorProfile
from app.utils.cashfree_payout import call_cashfree_transfer
from applications.earning.vendor_earning import (
    Beneficiary,
    VendorAccount,   
    PayoutTransaction,
    PayoutStatus,     
)


router = APIRouter(prefix="/vendor", tags=["Vendor Earnings"])

# class WithdrawRequest(BaseModel):
#     vendor: VendorProfile = Depends(vendor_required)
#     beneficiary_id: int
#     amount: Decimal = Field(..., gt=Decimal("0.99"))



@router.post("/vendor_account")
async def vendor_account(
    vendor: User = Depends(vendor_required),
    period: str = Query(
        None,
        description="Predefined period to filter earnings: 'this_month', 'this_week', 'this_year'"
    )
):
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile

    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_account = await VendorAccount.filter(vendor_id=vendor_profile.id).first()
    if not vendor_account:
        vendor_account = await VendorAccount.create(vendor=vendor_profile)
        
    now = datetime.now()
    if period == "this_month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == "this_week":
        start_date = now - timedelta(days=now.weekday())  # Monday
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == "this_year":
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    else:
        start_date = datetime(2000, 1, 1)
        end_date = now

    start_date = datetime(2000, 1, 1)
    end_date = datetime.now()
    summery = await vendor_account.earnings_calculation(start_date, end_date)

    return {
        "vendor_id": vendor_profile.id,
        "withdrawable_balance": vendor_account.pending_balance, 
        "pending_balance": vendor_account.pending_balance,
        "total_earnings": summery["total_earnings"],
        "average_earnings": summery["average_earnings"],
        "total_orders": summery["total_orders"],
        "commission_earned": vendor_account.commission_earned,
        "platform_cost": vendor_account.platform_cost,
        "updated_at": vendor_account.updated_at
    }
    

@router.get("/status")
async def get_status():
    return {"status": "Vendor Earnings API is operational."}