from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from tortoise.transactions import in_transaction
from decimal import Decimal, ROUND_DOWN

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

@router.get("/status")
async def get_status():
    return {"status": "Vendor Earnings API is operational."}