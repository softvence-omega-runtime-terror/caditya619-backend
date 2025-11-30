# app/main.py
from fastapi import FastAPI, APIRouter, HTTPException, Request
from pydantic import BaseModel, validator
import httpx
import uuid
import re

from app.config import settings

app = FastAPI(title="FastAPI Cashfree Example")

# Dummy product store
PRODUCTS = {
    1: {"name": "Test Product", "price": 100.0, "currency": "INR"}
}

# Cashfree Config
CASHFREE_CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV=="SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2022-01-01"

# In-memory order DB for testing
ORDERS_DB = {}

# Pydantic Models
class OrderRequest(BaseModel):
    product_id: int
    customer_name: str
    customer_email: str
    customer_phone: str
    return_url: str

    @validator("customer_phone")
    def validate_phone(cls, v):
        # Remove spaces, dashes
        phone = re.sub(r"[^\d+]", "", v)
        # Indian phone number (10 digits) or international with + and 10-15 digits
        if re.match(r"^(\+?\d{10,15})$", phone):
            return phone
        raise ValueError("Invalid phone number format. Example: Indian +919090407368, 9090407368 or International +16014635923")

router = APIRouter(prefix='/payment', tags=['Payment'])

@router.post("/create-order/")
async def create_order(req: OrderRequest):
    # Validate product
    product = PRODUCTS.get(req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Generate unique order id for your system
    order_id = str(uuid.uuid4())

    headers = {
        "x-client-id": CASHFREE_CLIENT_ID,
        "x-client-secret": CASHFREE_CLIENT_SECRET,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json"
    }

    payload = {
        "order_id": order_id,
        "order_amount": str(product["price"]),
        "order_currency": product["currency"],
        "customer_details": {
            "customer_id": str(uuid.uuid4()),
            "customer_name": req.customer_name,
            "customer_email": req.customer_email,
            "customer_phone": req.customer_phone,
        },
        "order_meta": {
            "return_url": req.return_url
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{CASHFREE_BASE}/orders", json=payload, headers=headers)

    data = resp.json()
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=data)

    # Save order in memory (simulate DB)
    ORDERS_DB[order_id] = {
        "product": product,
        "status": "created",
        "customer": req.dict(),
        "cashfree_data": data
    }

    return {
        "order_id": order_id,
        "payment_session_id": data.get("payment_session_id"),
        "payment_url": data.get("payment_link")
    }

@router.post("/webhook/cashfree/")
async def cashfree_webhook(request: Request):
    payload = await request.json()
    order_id = payload.get("order_id")
    status = payload.get("order_status")

    if order_id in ORDERS_DB:
        ORDERS_DB[order_id]["status"] = status

    return {"status": "ok", "received_order_id": order_id, "status_from_cashfree": status}

# Include router
app.include_router(router)

# Test root endpoint
@app.get("/")
def read_root():
    return {"message": "FastAPI + Cashfree Sandbox Example"}
