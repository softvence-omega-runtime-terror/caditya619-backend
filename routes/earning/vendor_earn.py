from fastapi import APIRouter, Depends, Query, HTTPException
import requests
import time
import base64
from pydantic import BaseModel
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from applications.user.models import User
from datetime import datetime, timedelta
from app.config import settings
from app.auth import vendor_required
from app.utils.generate_pdf import generate_payout_pdf
from app.utils.cashfree_payout import call_cashfree_transfer
from applications.earning.vendor_earning import (
    Beneficiary,
    VendorAccount,   
    PayoutTransaction,
    PayoutStatus,     
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

@router.get("/generate-pdf")
async def generate_pdf(vendor: User = Depends(vendor_required)):
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile
    transaction = await PayoutTransaction.filter(vendor_id=vendor_profile.id).first()
    if not transaction:
        return {"error": "Transaction not found"}
    file_url = await generate_payout_pdf(transaction)

    return {
        "message": "PDF generated successfully",
        "invoice_url": file_url,
    }

@router.get("/vendor_account")
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
    total_pending = summery["total_earnings"] - summery["total_withdrawn"]

    return {
        "vendor_id": vendor_profile.id,
        # Earning Page
        "total_earnings": summery["total_earnings"],
        "average_earnings": summery["average_earnings"],
        "total_orders": summery["total_orders"],
        "total_withdraw": summery["total_withdrawn"],
        "total_pending": total_pending,
        
        "pending_balance": await vendor_account.pending_balance_calculation(),
        "commission_earned": vendor_account.commission_earned,
        "platform_cost": vendor_account.platform_cost,
        "updated_at": vendor_account.updated_at
    }
    

def generate_signature():
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
class Beneficiary(BaseModel):
    beneficiary_name: str
    bank_account_number: str
    bank_ifsc: str
    email: str
    phone: str


@router.post("/add_beneficiary")
async def add_beneficiary(payload: Beneficiary, vendor: User = Depends(vendor_required)):
    signature, timestamp = generate_signature()

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
        await Beneficiary.create(
            vendor_id=vendor.id,
            beneficiary_id=unique_beneficiary_id,
            name=payload.name,
            bank_account_number=payload.bank_account_number,
            bank_ifsc=payload.bank_ifsc,
            email=payload.email,
            phone=payload.phone,
        )
    else:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    return res.json()


@router.post("/transfer")
async def transfer_amount(amount:int= None, vendor: User = Depends(vendor_required)):
    signature, timestamp = generate_signature()
    await vendor.fetch_related("vendor_profile")
    vendor_profile = vendor.vendor_profile
    
    beneficiary = await Beneficiary.filter(vendor_id=vendor_profile.id).first()
    if not vendor_account:
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




