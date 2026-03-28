import time
import hmac
import hashlib
import base64
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

router = APIRouter(prefix="/payout", tags=["Cashfree Payouts"])
#
CLIENT_ID = settings.CASHFREE_CLIENT_PAYOUT_ID
CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYOUT_SECRET
CASHFREE_PUBLIC_KEY = settings.CASHFREE_PUBLIC_KEY

BASE_URL = "https://sandbox.cashfree.com/payout"


# {
#   "beneficiary_id": "moynul2_m",
#   "beneficiary_name": "Moynul Islam",
#   "bank_account_number": "026291800001191",
#   "bank_ifsc": "YESB0000262",
#   "email": "softvence.moynul@gmail.com",
#   "phone": "+919876543210"
# }


def generate_signature():
    timestamp = int(time.time())
    sign_string = f"{CLIENT_ID}.{timestamp}".encode()

    public_key = serialization.load_pem_public_key(CASHFREE_PUBLIC_KEY.encode())

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
    beneficiary_id: str
    beneficiary_name: str
    bank_account_number: str
    bank_ifsc: str
    email: str
    phone: str


@router.post("/add_beneficiary")
def add_beneficiary(payload: Beneficiary):
    signature, timestamp = generate_signature()

    url = f"{BASE_URL}/beneficiary"

    headers = {
        "x-api-version": "2024-01-01",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
        "x-cf-signature": signature,
        "x-cf-timestamp": timestamp,
        "Content-Type": "application/json",
    }

    body = {
        "beneficiary_id": payload.beneficiary_id,
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

    if res.status_code not in [200, 201]:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    return res.json()


# -----------------------------------------------------
#   PAYOUT TRANSFER
# -----------------------------------------------------
class PayoutRequest(BaseModel):
    beneficiary_id: str
    amount: float
    transfer_id: str


@router.post("/transfer")
def transfer_amount(payload: PayoutRequest):
    signature, timestamp = generate_signature()

    url = f"{BASE_URL}/transfers"

    headers = {
        "x-api-version": "2024-01-01",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
        "x-cf-signature": signature,
        "x-cf-timestamp": timestamp,
        "Content-Type": "application/json",
    }

    body = {
        "transfer_id": payload.transfer_id,
        "transfer_amount": payload.amount,
        "beneficiary_details": {
            "beneficiary_id": payload.beneficiary_id
        },
        # optionally:
        "transfer_mode": "banktransfer",
        "currency": "INR",
        "transfer_remarks": "some remarks"
    }

    # body = {
    #     "transfer_id": payload.transfer_id,
    #     "beneficiary_id": payload.beneficiary_id,
    #     "amount": int(payload.amount * 100),
    #     "currency": "INR",
    #     "purpose": "payout",
    #     "remarks": "FastAPI payout test"
    # }

    res = requests.post(url, json=body, headers=headers)

    if res.status_code not in [200, 201]:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    return res.json()

