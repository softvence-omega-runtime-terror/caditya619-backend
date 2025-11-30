import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings

payout_router = APIRouter(prefix="/payout", tags=["Payout Sandbox"])

CLIENT_ID = settings.CLIENT_ID
CLIENT_SECRET = settings.SANDBOX_CLIENT_SECRET
BASE_URL = "https://payout-gamma.cashfree.com/payout/v1"


# -----------------------------------------------------
#   AUTH TOKEN
# -----------------------------------------------------
@payout_router.post("/auth")
def auth_token():
    url = f"{BASE_URL}/authorize"
    headers = {
        "X-Client-Id": CLIENT_ID,
        "X-Client-Secret": CLIENT_SECRET,
        "Content-Type": "application/json",
    }

    res = requests.post(url, headers=headers)
    data = res.json()

    if res.status_code != 200:
        raise HTTPException(status_code=400, detail=data)

    return data


# -----------------------------------------------------
#   ADD BENEFICIARY
# -----------------------------------------------------
class Beneficiary(BaseModel):
    beneId: str
    name: str
    email: str
    phone: str
    bankAccount: str
    ifsc: str


@payout_router.post("/add_beneficiary")
def add_beneficiary(payload: Beneficiary):
    token = auth_token()["data"]["token"]

    url = f"{BASE_URL}/addBeneficiary"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "beneId": payload.beneId,
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "bankAccount": payload.bankAccount,
        "ifsc": payload.ifsc,
        "address1": "Test Address",
        "city": "Test City",
        "state": "KA",
        "pincode": "560001"
    }

    res = requests.post(url, json=body, headers=headers)
    return res.json()


# -----------------------------------------------------
#   REQUEST PAYOUT
# -----------------------------------------------------
class PayoutRequest(BaseModel):
    beneId: str
    amount: float
    transferId: str


@payout_router.post("/transfer")
def transfer_money(payload: PayoutRequest):
    token = auth_token()["data"]["token"]

    url = f"{BASE_URL}/requestTransfer"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "beneId": payload.beneId,
        "amount": payload.amount,
        "transferId": payload.transferId,
        "transferMode": "banktransfer",
        "remarks": "Test Sandbox Payout",
    }

    res = requests.post(url, json=body, headers=headers)
    return res.json()
