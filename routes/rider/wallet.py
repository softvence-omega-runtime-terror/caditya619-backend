# routes/wallet.py
# from fastapi import APIRouter, Depends, HTTPException
# from app.utils.razorpay_client import client, get_or_create_fund_account
# from app.utils.firebase_push import send_scheduled_push
# from .scheduled_notifications import notify_withdrawal_success
# from applications.user.rider import RiderProfile, Withdrawal
# from app.token import get_current_user
# from applications.user.models import User
# import asyncio
# from decimal import Decimal, ROUND_DOWN, InvalidOperation



# router = APIRouter(tags=['Rider Wallet'])



# routers/withdrawal.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from decimal import Decimal
from applications.user.rider import RiderProfile as Rider, Withdrawal
from applications.user.models import User
from app.token import get_current_user
from app.utils.razorpay_client import get_or_create_fund_account, client, RAZORPAY_X_ACCOUNT_NUMBER
# from app.utils.firebase_push import send_scheduled_push  # We'll add this next
import uuid
import logging
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/withdrawal", tags=["Withdrawal"])
logger = logging.getLogger(__name__)


class WithdrawalRequest(BaseModel):
    amount: Decimal  # in rupees


@router.post("/request")
async def request_withdrawal(
    req: WithdrawalRequest,
    current_user: User = Depends(get_current_user)
):
    rider = await Rider.get(user=current_user)
    
    if not rider.is_bank_verified:
        raise HTTPException(400, "Bank account not verified")

    if rider.current_balance < req.amount:
        raise HTTPException(400, "Insufficient balance")

    if req.amount < Decimal("100"):
        raise HTTPException(400, "Minimum withdrawal is ₹100")

    # Create withdrawal record
    withdrawal = await Withdrawal.create(
        rider=rider,
        amount=req.amount,
        status="processing"
    )

    try:
        fund_account = get_or_create_fund_account(rider)
        if not fund_account:
            raise Exception("Failed to setup bank account")

        # Create actual payout
        payout = client.payout.create({
            "account_number": RAZORPAY_X_ACCOUNT_NUMBER,
            "fund_account_id": fund_account["id"],
            "amount": int(req.amount * 100),  # paise
            "currency": "INR",
            "mode": "IMPS",
            "purpose": "payout",
            "queue_if_low_balance": True,
            "reference_id": str(withdrawal.id),
        })

        # Success → Deduct balance
        rider.current_balance -= req.amount
        await rider.save()

        withdrawal.status = "completed"
        await withdrawal.save()

        # Send FCM notification
        # await send_scheduled_push(
        #     rider_id=rider.id,
        #     title="Withdrawal Successful!",
        #     body=f"₹{req.amount} has been sent to your bank account.",
        #     data={"type": "withdrawal_success", "amount": str(req.amount)}
        # )

        return {
            "success": True,
            "message": "Withdrawal successful",
            "payout_id": payout["id"],
            "amount": req.amount
        }

    except Exception as e:
        withdrawal.status = "failed"
        await withdrawal.save()

        # await send_scheduled_push(
        #     rider_id=rider.id,
        #     title="Withdrawal Failed",
        #     body="There was an issue processing your withdrawal. Please try again.",
        #     data={"type": "withdrawal_failed"}
        # )

        logger.error(f"Withdrawal failed for rider {rider.id}: {e}")
        raise HTTPException(500, "Withdrawal failed. Please try again.")


# @router.post("/withdraw/")
# async def withdraw_request(
#     amount: float,
#     user: User = Depends(get_current_user)
# ):
#     rider = await RiderProfile.get(user=user)
#     try:
#         amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
#     except (InvalidOperation, TypeError):
#         raise HTTPException(status_code=400, detail="Invalid amount")
#     if amount < 100:
#         raise HTTPException(400, "Minimum withdrawal ₹100")
#     if amount > rider.current_balance:
#         raise HTTPException(400, "Insufficient balance")
#     if not rider.bank_account_number or not rider.bank_ifsc:
#         raise HTTPException(400, "Add bank account first")

#     # Create withdrawal record
#     withdrawal = await Withdrawal.create(
#         rider=rider,
#         amount=amount,
#         status="processing"
#     )

#     # Hold money
#     rider.current_balance -= amount
#     await rider.save()

#     # Background payout
#     asyncio.create_task(process_razorpay_payout(withdrawal.id))
    
#     return {
#         "message": "Withdrawal requested",
#         "amount": amount,
#         "status": "processing"
#     }

# # Background task
# async def process_razorpay_payout(withdrawal_id: int):
#     withdrawal = await Withdrawal.get(id=withdrawal_id)
#     #rider = withdrawal.rider
#     rider = await RiderProfile.get(id=withdrawal.rider_id)

#     print("Processing payout for withdrawal:", withdrawal.id)

#     try:
#         fund_account = get_or_create_fund_account(rider)
#         print("Fund Account:", fund_account, "before payout")

#         payout = client.payout.create({
#             "account_number": "23232300123456",  # Your RazorpayX account
#             "fund_account_id": fund_account["id"],
#             "amount": int(withdrawal.amount * 100),  # in paise
#             "currency": "INR",
#             "mode": "IMPS",
#             "purpose": "rider_payout",
#             "queue_if_low_balance": True,
#             "reference_id": str(withdrawal.id)
#         })

#         # Update status
#         withdrawal.status = "completed"
#         await withdrawal.save()

#         print("Payout successful:", payout)

#         # Send push
#         # await send_scheduled_push(
#         #     rider_id=rider.id,
#         #     title="Withdrawal Successful!",
#         #     body=f"₹{withdrawal.amount} sent to your bank instantly",
#         #     data={"type": "withdrawal"}
#         # )

#         # Optional: Celery task
#         notify_withdrawal_success.delay(withdrawal.id)

#     except Exception as e:
#         withdrawal.status = "failed"
#         await withdrawal.save()

#         # Refund
#         rider.current_balance += withdrawal.amount
#         await rider.save()

#         # await send_scheduled_push(
#         #     rider_id=rider.id,
#         #     title="Withdrawal Failed",
#         #     body="Contact support",
#         #     data={"type": "error"}
#         # )




@router.post("/bank/add/")
async def add_bank(
    account_number: str,
    ifsc: str,
    holder_name: str,
    user: User = Depends(get_current_user),
):
    rider = await Rider.get(user=user)
    rider.bank_account_number = account_number
    rider.bank_ifsc = ifsc
    rider.bank_holder_name = holder_name
    rider.is_bank_verified = True
    await rider.save()

    return {"message": "Bank added successfully"}