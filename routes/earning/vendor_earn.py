from fastapi import APIRouter, Depends, Query, HTTPException
import requests
import time
import base64
from pydantic import BaseModel
from typing import Optional
from applications.user.models import User
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.auth import vendor_required
from applications.earning.vendor_earning import (
    Beneficiary as BeneficiaryModel,
    get_or_create_vendor_account,
)


router = APIRouter(prefix="/vendor", tags=["Vendor Earnings"])

CLIENT_ID = settings.CASHFREE_CLIENT_PAYOUT_ID
CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYOUT_SECRET
PUBLIC_KEY = settings.CASHFREE_PUBLIC_KEY

BASE_URL = "https://sandbox.cashfree.com/payout"

# class WithdrawRequest(BaseModel):
#     vendor: VendorProfile = Depends(vendor_required)
#     beneficiary_id: int
#     amount: Decimal = Field(..., gt=Decimal("0.99"))

class DummyTransaction:
    def __init__(self):
        self.transfer_id = "TXN_TEST_001"
        self.amount = 1500.75
        self.status = "SUCCESS"
        self.created_at = datetime.now()


@router.get("/vendor_account")
async def vendor_account(
    vendor: User = Depends(vendor_required),
    period: Optional[str] = Query(
        None,
        description="Predefined period to filter earnings: 'this_month', 'this_week', 'this_year'"
    )
):
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile

    if not vendor_profile:
        return {"error": "Vendor profile not found"}

    vendor_account = await get_or_create_vendor_account(vendor_profile)
    now = datetime.now(timezone.utc)
    last_sync = vendor_account.last_withdrawable_sync_at
    if last_sync is not None and last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)

    # Apply withdrawal balance release in 7-day batches.
    if last_sync is None or last_sync <= now - timedelta(days=7):
        await vendor_account.refresh_balances(reference_time=now)

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
        start_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
        end_date = now

    summary = await vendor_account.earnings_calculation(start_date, end_date)
    total_pending = summary["total_earnings"] - summary["total_withdrawn"]

    return {
        "vendor_id": vendor_profile.id,
        # Earning Page
        "total_earnings": summary["total_earnings"],
        "average_earnings": summary["average_earnings"],
        "total_orders": summary["total_orders"],
        "total_withdraw": summary["total_withdrawn"],
        "total_pending": total_pending,
        
        "available_for_withdraw": vendor_account.available_for_withdraw,
        "pending_balance": await vendor_account.pending_balance_calculation(),
        "updated_at": vendor_account.updated_at
    }


@router.post("/vendor_account/sync_now")
async def vendor_account_sync_now(vendor: User = Depends(vendor_required)):
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    vendor_account = await get_or_create_vendor_account(vendor_profile)
    now = datetime.now(timezone.utc)
    summary = await vendor_account.refresh_balances(reference_time=now)

    return {
        "success": True,
        "vendor_id": vendor_profile.id,
        "total_earnings": summary["total_earnings"],
        "matured_earnings": summary["matured_earnings"],
        "release_window_earnings": summary["release_window_earnings"],
        "total_withdrawn": summary["total_withdrawn"],
        "available_for_withdraw": summary["available_for_withdraw"],
        "synced_at": vendor_account.last_withdrawable_sync_at,
        "updated_at": vendor_account.updated_at,
    }







def generate_signature():
    # Keep crypto import lazy so this module can load even if payout dependencies are missing.
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    timestamp = int(time.time())
    sign_string = f"{CLIENT_ID}.{timestamp}".encode()

    public_key = serialization.load_pem_public_key(PUBLIC_KEY.encode())

    encrypted = public_key.encrypt(
        sign_string,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        )
    )
    signature = base64.b64encode(encrypted).decode()
    return signature, str(timestamp)

# -----------------------------------------------------
#   ADD BENEFICIARY
# -----------------------------------------------------
class BeneficiaryPayload(BaseModel):
    beneficiary_name: str
    bank_account_number: str
    bank_ifsc: str
    email: str
    phone: str


@router.post("/add_beneficiary")
async def add_beneficiary(payload: BeneficiaryPayload, vendor: User = Depends(vendor_required)):
    signature, timestamp = generate_signature()
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    url = f"{BASE_URL}/beneficiary"
    unique_beneficiary_id = f"QU{vendor.id}{int(time.time())}"

    headers = {
        "x-api-version": "2024-01-01",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
        "x-cf-signature": signature,
        "x-cf-timestamp": timestamp,
        "Content-Type": "application/json",
    }

    body = {
        "beneficiary_id": unique_beneficiary_id,
        "beneficiary_name": payload.beneficiary_name,
        "beneficiary_instrument_details": {
            "bank_account_number": payload.bank_account_number,
            "bank_ifsc": payload.bank_ifsc,
        },
        "beneficiary_contact_details": {
            "beneficiary_email": payload.email,
            "beneficiary_phone": payload.phone,
            "beneficiary_country_code": "+91",
        },
    }

    res = requests.post(url, json=body, headers=headers)

    if res.status_code in [200, 201]:
        await BeneficiaryModel.create(
            vendor_id=vendor_profile.id,
            beneficiary_id=unique_beneficiary_id,
            name=payload.beneficiary_name,
            bank_account_number=payload.bank_account_number,
            bank_ifsc=payload.bank_ifsc,
            email=payload.email,
            phone=payload.phone,
        )
    else:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    return res.json()


@router.post("/withdraw")
async def withdraw_amount(
    amount: Optional[int] = Query(None, ge=1),
    vendor: User = Depends(vendor_required),
):
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")

    signature, timestamp = generate_signature()
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile
    
    beneficiary = await BeneficiaryModel.filter(vendor_id=vendor_profile.id).first()
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiary account not found")

    url = f"{BASE_URL}/transfers"
    unique_transfer_id = f"QU{vendor.id}{int(time.time())}"

    headers = {
        "x-api-version": "2024-01-01",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
        "x-cf-signature": signature,
        "x-cf-timestamp": timestamp,
        "Content-Type": "application/json",
    }

    body = {
        "transfer_id": unique_transfer_id,
        "transfer_amount": amount,
        "beneficiary_details": {
            "beneficiary_id": beneficiary.beneficiary_id,
            "email": beneficiary.email,
            "phone": beneficiary.phone
        },
        "transfer_mode": "banktransfer",
        "currency": "INR",
        "transfer_remarks": beneficiary.name
    }
    res = requests.post(url, json=body, headers=headers)

    if res.status_code not in [200, 201]:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    return res.json()

