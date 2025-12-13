# routes/payment/payment_helper.py or add this to routes.payment.payment.py

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
CASHFREE_API_VERSION = "2023-08-01"


async def create_payment_session_for_orders(orders: List[Order]):
    """
    Create Cashfree payment session for Flutter SDK integration.
    Calls Cashfree /orders API to get payment_session_id and cf_order_id.
    
    API Documentation: https://docs.cashfree.com/reference/pgcreateorder
    """
    
    print(f"🔄 Starting payment session creation for {len(orders)} order(s)")
    
    # Calculate total amount
    total_amount = sum(float(order.total) for order in orders)
    print(f"💰 Total amount: {total_amount}")
    
    # Generate unique order ID
    order_id = f"ORDER_{uuid.uuid4().hex[:12].upper()}"
    print(f"🆔 Generated order_id: {order_id}")
    
    # Get customer details from first order
    customer_info = orders[0].metadata.get("shipping_address", {})
    user = orders[0].user if hasattr(orders[0], 'user') else None
    
    customer_phone = customer_info.get("phone_number", "9999999999")
    customer_name = customer_info.get("full_name", "Customer")
    customer_email = getattr(user, 'email', None) or "customer@example.com"
    
    print(f"👤 Customer: {customer_name} | Phone: {customer_phone} | Email: {customer_email}")
    
    # Prepare request payload for Cashfree
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
        "order_meta": {
            "return_url": f"{settings.FRONTEND_URL}/payment/callback",
            "notify_url": f"{settings.BACKEND_URL}/api/payment/webhook"
        },
        "order_note": f"Payment for {len(orders)} order(s)"
    }
    
    print(f"📦 Payload prepared:")
    print(f"   - Order ID: {payload['order_id']}")
    print(f"   - Amount: {payload['order_amount']}")
    print(f"   - Return URL: {payload['order_meta']['return_url']}")
    print(f"   - Notify URL: {payload['order_meta']['notify_url']}")
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "x-api-version": CASHFREE_API_VERSION,
        "x-client-id": CASHFREE_CLIENT_PAYMENT_ID,
        "x-client-secret": CASHFREE_CLIENT_PAYMENT_SECRET
    }
    
    print(f"🔐 Using credentials:")
    print(f"   - Client ID: {CASHFREE_CLIENT_PAYMENT_ID[:10]}...")
    print(f"   - Environment: {CASHFREE_ENV}")
    print(f"   - Base URL: {CASHFREE_BASE}")
    
    try:
        print(f"🌐 Making request to: {CASHFREE_BASE}/orders")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CASHFREE_BASE}/orders",
                json=payload,
                headers=headers
            )
            
            print(f"📡 Response Status: {response.status_code}")
            print(f"📡 Response Body: {response.text}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                print(f"✅ Cashfree order created successfully")
                print(f"   Order ID: {data.get('order_id')}")
                print(f"   CF Order ID: {data.get('cf_order_id')}")
                print(f"   Payment Session ID: {data.get('payment_session_id')}")
                
                # Return session details for Flutter SDK
                return {
                    "payment_session_id": data.get("payment_session_id"),
                    "cf_order_id": data.get("cf_order_id"),
                    "order_id": data.get("order_id"),
                    "order_status": data.get("order_status", "ACTIVE")
                }
            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("message", response.text)
                print(f"❌ Cashfree API Error [{response.status_code}]: {error_msg}")
                print(f"📋 Full error response: {error_data}")
                raise Exception(f"Cashfree API error: {error_msg}")
                
    except httpx.TimeoutException:
        print("⏱️ Cashfree API timeout")
        raise Exception("Payment gateway timeout. Please try again.")
    except httpx.RequestError as e:
        print(f"🌐 Network error calling Cashfree: {e}")
        raise Exception(f"Payment gateway connection failed: {str(e)}")
    except Exception as e:
        print(f"⚠️ Error creating Cashfree payment session: {e}")
        raise