# routes/payment/payment_helper.py

import httpx
import uuid
from typing import List
from applications.customer.models import Order
from app.config import settings

# Cashfree Configuration
CASHFREE_CLIENT_PAYMENT_ID = settings.CASHFREE_CLIENT_PAYMENT_ID
CASHFREE_CLIENT_PAYMENT_SECRET = settings.CASHFREE_CLIENT_PAYMENT_SECRET
CASHFREE_ENV = settings.CASHFREE_ENV
CASHFREE_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "SANDBOX" else "https://api.cashfree.com/pg"
CASHFREE_API_VERSION = "2023-08-01"  # ✅ Fixed: Use 2023-08-01, not 2025-01-01


async def create_payment_session_for_orders(orders: List[Order]):
    """
    Create Cashfree payment session for Flutter SDK integration.
    """
    
    total_amount = sum(float(order.total) for order in orders)
    #order_id = f"ORDER_{uuid.uuid4().hex[:12].upper()}"
    order_id = orders[0].payment_id or f"PAY_{uuid.uuid4().hex[:12].upper()}"
    
    customer_info = orders[0].metadata.get("shipping_address", {})
    user = orders[0].user if hasattr(orders[0], 'user') else None
    
    customer_phone = customer_info.get("phone_number", "9999999999")
    customer_name = customer_info.get("full_name", "Customer")
    customer_email = getattr(user, 'email', None) or "customer@example.com"
    
    payload = {
        "order_id": order_id,
        "order_amount": round(float(total_amount), 2),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(orders[0].user_id),
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "customer_email": customer_email
        },
        # "order_meta": {
        #     # ✅ Fixed: Correct URLs without double slashes
        #     "return_url": f"{settings.BACKEND_URL}/api/payment/test/pay-last",  # For testing
        #     "notify_url": f"{settings.BACKEND_URL}/api/payment/webhook"
        # },
        "order_note": f"Payment for {len(orders)} order(s)"
    }
    
    headers = {
        "Content-Type": "application/json",
        "x-api-version": CASHFREE_API_VERSION,
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CASHFREE_BASE}/orders",
                json=payload,
                headers=headers
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                # Extract IDs from Cashfree response
                cashfree_order_id = data.get("order_id")
                cf_order_id = data.get("cf_order_id")
                
                return {
                    "payment_session_id": data.get("payment_session_id"),
                    "order_id": cashfree_order_id,
                    "cf_order_id": cf_order_id,
                    "order_status": data.get("order_status", "ACTIVE")
                }
            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("message", response.text)
                raise Exception(f"Cashfree API error: {error_msg}")
                
    except httpx.TimeoutException:
        raise Exception("Payment gateway timeout. Please try again.")
    except httpx.RequestError as e:
        raise Exception(f"Payment gateway connection failed: {str(e)}")
    except Exception as e:
        raise