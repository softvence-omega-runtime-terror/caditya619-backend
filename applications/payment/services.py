# applications/payment/services.py

import razorpay
import hmac
import hashlib
import uuid
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from fastapi import HTTPException
from applications.customer.models import *

from applications.payment.models import (
    Payment, PaymentRefund, PaymentStatus, PaymentProvider
)
from config import settings  # Your app settings

class RazorpayService:
    """
    Service class to handle all Razorpay payment operations
    """
    
    def __init__(self):
        """
        Initialize Razorpay client with your credentials
        Get these from Razorpay Dashboard: https://dashboard.razorpay.com/app/keys
        """
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
    
    async def create_razorpay_order(
        self, 
        order_id: str, 
        amount: Decimal, 
        currency: str = "INR"
    ) -> Dict[str, Any]:
        """
        Step 1: Create a Razorpay order
        This happens when user clicks 'Pay Now' button
        
        Args:
            order_id: Your internal order ID
            amount: Order amount in your currency
            currency: Currency code (INR, USD, etc.)
        
        Returns:
            Dict containing Razorpay order details
        """
        try:
            # Get the order from database
            order = await Order.get(id=order_id)
            
            # Convert amount to paise (Razorpay uses smallest currency unit)
            # 1 INR = 100 paise
            amount_in_paise = int(amount * 100)
            
            # Create Razorpay order
            razorpay_order = self.client.order.create({
                "amount": amount_in_paise,
                "currency": currency,
                "receipt": order_id,  # Your internal order ID for reference
                "notes": {
                    "order_id": order_id,
                    "user_id": str(order.user_id)
                }
            })
            
            # Create payment record in your database
            payment_id = f"pay_{uuid.uuid4().hex[:12]}"
            payment = await Payment.create(
                id=payment_id,
                order_id=order_id,
                user_id=order.user_id,
                provider=PaymentProvider.RAZORPAY,
                provider_order_id=razorpay_order['id'],
                amount=amount,
                currency=currency,
                status=PaymentStatus.PENDING,
                metadata={
                    "razorpay_order": razorpay_order
                }
            )
            
            return {
                "razorpay_order_id": razorpay_order['id'],
                "razorpay_key_id": self.key_id,
                "amount": amount,
                "currency": currency,
                "order_id": order_id,
                "payment_id": payment_id
            }
            
        except Order.DoesNotExist:
            raise HTTPException(status_code=404, detail="Order not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to create Razorpay order: {str(e)}"
            )
    
    async def verify_payment(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        order_id: str
    ) -> Payment:
        """
        Step 2: Verify payment after user completes payment
        This ensures the payment is legitimate and not tampered
        
        Args:
            razorpay_order_id: Razorpay order ID
            razorpay_payment_id: Razorpay payment ID
            razorpay_signature: Signature to verify authenticity
            order_id: Your internal order ID
        
        Returns:
            Payment object
        """
        try:
            # Verify signature to ensure payment is authentic
            is_valid = self._verify_signature(
                razorpay_order_id,
                razorpay_payment_id,
                razorpay_signature
            )
            
            if not is_valid:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid payment signature"
                )
            
            # Get payment record
            payment = await Payment.filter(
                provider_order_id=razorpay_order_id,
                order_id=order_id
            ).first()
            
            if not payment:
                raise HTTPException(status_code=404, detail="Payment not found")
            
            # Fetch payment details from Razorpay
            razorpay_payment = self.client.payment.fetch(razorpay_payment_id)
            
            # Update payment record
            payment.provider_payment_id = razorpay_payment_id
            payment.provider_signature = razorpay_signature
            payment.status = PaymentStatus.COMPLETED
            payment.payment_method = razorpay_payment.get('method')
            payment.completed_at = datetime.utcnow()
            payment.metadata = {
                **payment.metadata,
                "razorpay_payment": razorpay_payment
            }
            await payment.save()
            
            # Update order status
            order = await Order.get(id=order_id)
            order.status = OrderStatus.CONFIRMED
            order.transaction_id = razorpay_payment_id
            await order.save()
            
            return payment
            
        except HTTPException:
            raise
        except Exception as e:
            # Update payment as failed
            if payment:
                payment.status = PaymentStatus.FAILED
                payment.error_description = str(e)
                await payment.save()
            
            raise HTTPException(
                status_code=500, 
                detail=f"Payment verification failed: {str(e)}"
            )
    
    def _verify_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """
        Verify Razorpay payment signature
        This prevents payment tampering
        """
        try:
            # Create signature verification string
            message = f"{razorpay_order_id}|{razorpay_payment_id}"
            
            # Generate expected signature
            generated_signature = hmac.new(
                self.key_secret.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(generated_signature, razorpay_signature)
            
        except Exception:
            return False
    
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None
    ) -> PaymentRefund:
        """
        Process refund for a payment
        
        Args:
            payment_id: Your internal payment ID
            amount: Amount to refund (None for full refund)
            reason: Reason for refund
        
        Returns:
            PaymentRefund object
        """
        try:
            # Get payment record
            payment = await Payment.get(id=payment_id)
            
            if payment.status != PaymentStatus.COMPLETED:
                raise HTTPException(
                    status_code=400, 
                    detail="Can only refund completed payments"
                )
            
            # Calculate refund amount
            refund_amount = amount if amount else payment.amount
            refund_amount_paise = int(refund_amount * 100)
            
            # Process refund via Razorpay
            razorpay_refund = self.client.payment.refund(
                payment.provider_payment_id,
                {
                    "amount": refund_amount_paise,
                    "notes": {
                        "reason": reason or "Refund requested"
                    }
                }
            )
            
            # Create refund record
            refund_id = f"rfnd_{uuid.uuid4().hex[:12]}"
            refund = await PaymentRefund.create(
                id=refund_id,
                payment_id=payment_id,
                provider_refund_id=razorpay_refund['id'],
                amount=refund_amount,
                reason=reason,
                status=PaymentStatus.COMPLETED,
                processed_at=datetime.utcnow()
            )
            
            # Update payment status if full refund
            if refund_amount == payment.amount:
                payment.status = PaymentStatus.REFUNDED
                await payment.save()
                
                # Update order status
                order = await Order.get(id=payment.order_id)
                order.status = OrderStatus.REFUNDED
                await order.save()
            
            return refund
            
        except Payment.DoesNotExist:
            raise HTTPException(status_code=404, detail="Payment not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Refund processing failed: {str(e)}"
            )
    
    async def get_payment_details(self, payment_id: str) -> Optional[Payment]:
        """
        Get payment details by ID
        """
        return await Payment.filter(id=payment_id).first()
    
    async def get_order_payments(self, order_id: str) -> list:
        """
        Get all payments for an order
        """
        return await Payment.filter(order_id=order_id).all()