# routes/payment.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from applications.payment.schemas import (
    CreateRazorpayOrderSchema,
    VerifyRazorpayPaymentSchema,
    RefundPaymentSchema,
    RazorpayOrderResponseSchema,
    PaymentVerificationResponseSchema,
    PaymentResponseSchema,
    RefundResponseSchema
)
from applications.payment.services import RazorpayService
from applications.payment.models import Payment
from app.token import get_current_user  # Your auth dependency
from applications.user.models import User
from applications.customer.models import *

router = APIRouter(prefix="/api/payments", tags=["Payments"])

# ============== PAYMENT CREATION ==============

@router.post(
    "/razorpay/create-order",
    response_model=RazorpayOrderResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Razorpay Order",
    description="Step 1: Create a Razorpay order to initiate payment process"
)
async def create_razorpay_order(
    order_data: CreateRazorpayOrderSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Creates a Razorpay order for payment processing
    
    Flow:
    1. User completes checkout
    2. Frontend calls this endpoint with order details
    3. Backend creates Razorpay order
    4. Returns Razorpay order ID and key for frontend
    5. Frontend opens Razorpay payment modal
    """
    service = RazorpayService()
    
    result = await service.create_razorpay_order(
        order_id=order_data.order_id,
        amount=order_data.amount,
        currency=order_data.currency
    )
    
    return {
        "success": True,
        **result
    }

# ============== PAYMENT VERIFICATION ==============

@router.post(
    "/razorpay/verify",
    response_model=PaymentVerificationResponseSchema,
    summary="Verify Razorpay Payment",
    description="Step 2: Verify payment after user completes payment in Razorpay modal"
)
async def verify_razorpay_payment(
    payment_data: VerifyRazorpayPaymentSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Verifies Razorpay payment after successful payment
    
    Flow:
    1. User completes payment in Razorpay modal
    2. Razorpay frontend SDK returns payment details
    3. Frontend sends these details to this endpoint
    4. Backend verifies signature and updates order status
    """
    service = RazorpayService()
    
    payment = await service.verify_payment(
        razorpay_order_id=payment_data.razorpay_order_id,
        razorpay_payment_id=payment_data.razorpay_payment_id,
        razorpay_signature=payment_data.razorpay_signature,
        order_id=payment_data.order_id
    )
    
    return {
        "success": True,
        "message": "Payment verified successfully",
        "payment_id": payment.id,
        "order_id": payment.order_id,
        "status": payment.status.value
    }

# ============== PAYMENT DETAILS ==============

@router.get(
    "/{payment_id}",
    response_model=PaymentResponseSchema,
    summary="Get Payment Details",
    description="Get detailed information about a specific payment"
)
async def get_payment(
    payment_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve payment details by payment ID
    """
    service = RazorpayService()
    payment = await service.get_payment_details(payment_id)
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Verify user owns this payment
    if payment.user_id != current_user.id:
        raise HTTPException(
            status_code=403, 
            detail="Not authorized to view this payment"
        )
    
    return PaymentResponseSchema.from_orm(payment)

@router.get(
    "/order/{order_id}",
    response_model=List[PaymentResponseSchema],
    summary="Get Order Payments",
    description="Get all payments associated with an order"
)
async def get_order_payments(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve all payments for a specific order
    Useful for checking payment history
    """
    service = RazorpayService()
    payments = await service.get_order_payments(order_id)
    
    if not payments:
        return []
    
    # Verify user owns this order
    if payments[0].user_id != current_user.id:
        raise HTTPException(
            status_code=403, 
            detail="Not authorized to view these payments"
        )
    
    return [PaymentResponseSchema.from_orm(payment) for payment in payments]

# ============== REFUNDS ==============

@router.post(
    "/refund",
    response_model=RefundResponseSchema,
    summary="Process Refund",
    description="Process a refund for a completed payment"
)
async def process_refund(
    refund_data: RefundPaymentSchema,
    current_user: User = Depends(get_current_user)
):
    """
    Process refund for a payment
    
    Note: This endpoint might be restricted to admin users only
    Add proper authorization checks based on your requirements
    """
    service = RazorpayService()
    
    refund = await service.refund_payment(
        payment_id=refund_data.payment_id,
        amount=refund_data.amount,
        reason=refund_data.reason
    )
    
    return {
        "success": True,
        "message": "Refund processed successfully",
        "refund_id": refund.id,
        "payment_id": refund.payment_id,
        "amount": refund.amount,
        "status": refund.status.value
    }

# ============== WEBHOOK (Optional but recommended) ==============

@router.post(
    "/razorpay/webhook",
    status_code=status.HTTP_200_OK,
    summary="Razorpay Webhook",
    description="Receive webhook events from Razorpay for payment updates"
)
async def razorpay_webhook(request: dict):
    """
    Handle Razorpay webhook events
    
    Webhooks are useful for:
    - Payment failures
    - Automatic refund updates
    - Payment disputes
    
    Setup webhooks in Razorpay Dashboard:
    https://dashboard.razorpay.com/app/webhooks
    
    Note: Add signature verification for production
    """
    event = request.get('event')
    payload = request.get('payload')
    
    # Handle different webhook events
    if event == 'payment.captured':
        # Payment was successfully captured
        payment_entity = payload.get('payment', {}).get('entity', {})
        # Update your payment record if needed
        pass
    
    elif event == 'payment.failed':
        # Payment failed
        payment_entity = payload.get('payment', {}).get('entity', {})
        # Update payment status to failed
        pass
    
    elif event == 'refund.created':
        # Refund was processed
        refund_entity = payload.get('refund', {}).get('entity', {})
        # Update refund record
        pass
    
    return {"status": "success"}