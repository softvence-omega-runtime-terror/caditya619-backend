import httpx
from app.config import settings

CASHFREE_CLIENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2025-01-01"

async def verify_payment_status(order_id: str):
    """
    Calls Cashfree to get status of an order.
    """
    url = f"{CASHFREE_BASE}/orders/{order_id}"
    headers = {
        "x-api-version": CASHFREE_API_VERSION,
        "x-client-id": CASHFREE_CLIENT_ID,
        "x-client-secret": CASHFREE_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "order_status": data.get("order_status"),
                "cf_order_id": data.get("cf_order_id"),
                "order_amount": data.get("order_amount"),
                "payment_session_id": data.get("payment_session_id")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
