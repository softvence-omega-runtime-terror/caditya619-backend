# applications/payment/services.py

import os
import time
import httpx
from decimal import Decimal

class PaymentService:
    """Service to handle all Cashfree payment operations using REST API"""
    
    BASE_URL = "https://sandbox.cashfree.com/pg"  # Use production URL for live
    
    @staticmethod
    def _get_headers():
        """Get Cashfree API headers"""
        return {
            "x-client-id": os.getenv("CASHFREE_APP_ID"),
            "x-client-secret": os.getenv("CASHFREE_SECRET_KEY"),
            "x-api-version": os.getenv("CASHFREE_API_VERSION", "2023-08-01"),
            "Content-Type": "application/json"
        }
    
    @staticmethod
    async def create_cashfree_order(order, current_user) -> dict:
        """Create Cashfree payment order using REST API"""
        try:
            # Generate unique Cashfree order ID
            cf_order_id = f"CF_{order.id}_{int(time.time())}"
            
            # Prepare order data
            order_data = {
                "order_id": cf_order_id,
                "order_amount": float(order.total),
                "order_currency": "INR",
                "customer_details": {
                    "customer_id": str(current_user.id),
                    "customer_email": getattr(current_user, 'email', 'customer@example.com'),
                    "customer_phone": order.shipping_address.phone_number if order.shipping_address else "9999999999",
                    "customer_name": order.shipping_address.full_name if order.shipping_address else "Customer"
                },
                "order_meta": {
                    "return_url": f"{os.getenv('PAYMENT_RETURN_URL')}?order_id={order.id}",
                    "notify_url": f"{os.getenv('PAYMENT_RETURN_URL')}/webhook"
                }
            }
            
            # Call Cashfree API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{PaymentService.BASE_URL}/orders",
                    json=order_data,
                    headers=PaymentService._get_headers(),
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise ValueError(f"Cashfree API error: {response.text}")
                
                result = response.json()
            
            # Update order with Cashfree details
            order.cf_order_id = cf_order_id
            order.payment_session_id = result.get("payment_session_id")
            order.payment_status = "unpaid"
            await order.save()
            
            return {
                "success": True,
                "payment_session_id": result.get("payment_session_id"),
                "cf_order_id": cf_order_id,
                "payment_url": result.get("payment_link"),
                "order_id": order.id
            }
            
        except Exception as e:
            print(f"Cashfree order creation error: {e}")
            raise ValueError(f"Payment initialization failed: {str(e)}")
    
    
    @staticmethod
    async def verify_payment(cf_order_id: str) -> dict:
        """Verify payment status from Cashfree"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{PaymentService.BASE_URL}/orders/{cf_order_id}",
                    headers=PaymentService._get_headers(),
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise ValueError(f"Cashfree API error: {response.text}")
                
                result = response.json()
            
            return {
                "order_id": result.get("order_id"),
                "order_status": result.get("order_status"),
                "payment_status": result.get("order_status"),
                "transaction_id": result.get("cf_order_id"),
                "order_amount": result.get("order_amount")
            }
            
        except Exception as e:
            print(f"Payment verification error: {e}")
            raise ValueError(f"Payment verification failed: {str(e)}")
    
    
    @staticmethod
    async def handle_payment_callback(order_id: str, cf_order_id: str):
        """Handle payment callback and update order"""
        try:
            from applications.customer.models import Order, OrderStatus
            
            # Get order
            order = await Order.get(id=order_id).prefetch_related("items__item", "shipping_address")
            
            # Verify payment with Cashfree
            payment_data = await PaymentService.verify_payment(cf_order_id)
            
            # Update order based on payment status
            if payment_data["order_status"] == "PAID":
                order.payment_status = "paid"
                order.status = OrderStatus.CONFIRMED
                order.transaction_id = payment_data.get("transaction_id")
            elif payment_data["order_status"] in ["FAILED", "CANCELLED"]:
                order.payment_status = "failed"
                order.status = OrderStatus.CANCELLED
                
                # Restore stock on failed payment
                for order_item in order.items:
                    item = order_item.item
                    item.stock += order_item.quantity
                    item.total_sale -= order_item.quantity
                    await item.save()
            else:
                order.payment_status = "pending"
            
            await order.save()
            return order
            
        except Exception as e:
            print(f"Payment callback error: {e}")
            raise ValueError(f"Payment callback processing failed: {str(e)}")