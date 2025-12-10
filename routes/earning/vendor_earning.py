# from fastapi import APIRouter, HTTPException, Depends
# from pydantic import BaseModel, Field
# from tortoise.transactions import in_transaction
# from decimal import Decimal, ROUND_DOWN
# import uuid
# from app.auth import vendor_required
# import inspect
# import asyncio

# from applications.user.vendor import VendorProfile as Vendor
# from applications.earning.vendor_earning import (
#     Beneficiary,
#     VendorAccount,   
#     PayoutTransaction,
#     PayoutStatus,     
# )


# from app.utils.cashfree_payout import call_cashfree_transfer
# router = APIRouter(prefix="/vendor_earning", tags=["Earnings"])

# class WithdrawRequest(BaseModel):
#     vendor: Vendor = Depends(vendor_required)
#     beneficiary_id: int
#     amount: Decimal = Field(..., gt=Decimal("0.99"))


# @router.post("/request_withdraw")
# async def request_withdraw(
#     req: WithdrawRequest,
    
# ):
#     vendor = await Vendor.get_or_none(id=req.vendor_id)
#     if not vendor:
#         raise HTTPException(status_code=404, detail="vendor not found")

#     ledger = await VendorAccount.get_or_none(vendor=vendor)
#     if not ledger:
#         raise HTTPException(status_code=400, detail="ledger missing")

#     # ensure Decimal type
#     amount = Decimal(str(req.amount)).quantize(Decimal("0.01"))

#     # Compare decimals safely
#     if Decimal(ledger.withdrawable_balance) < amount:
#         raise HTTPException(status_code=400, detail="insufficient withdrawable balance")

#     beneficiary = await Beneficiary.get_or_none(
#         id=req.beneficiary_id, vendor=vendor, is_active=True
#     )
#     if not beneficiary:
#         raise HTTPException(status_code=400, detail="beneficiary not found")

#     # unique transfer id for CF (24 hex chars after prefix)
#     transfer_id = f"txn_{uuid.uuid4().hex[:24]}"

#     # create transaction + move withdrawable → pending inside a DB transaction
#     async with in_transaction():
#         await PayoutTransaction.create(
#             vendor=vendor,
#             beneficiary=beneficiary,
#             transfer_id=transfer_id,
#             amount=amount,
#             status=PayoutStatus.QUEUED,
#         )

#         # use Decimal arithmetic and quantize to 2 decimal places
#         ledger.withdrawable_balance = (
#             Decimal(ledger.withdrawable_balance) - amount
#         ).quantize(Decimal("0.01"))
#         ledger.pending_balance = (
#             Decimal(ledger.pending_balance) + amount
#         ).quantize(Decimal("0.01"))

#         await ledger.save()

#     return {
#         "transfer_id": transfer_id,
#         "status": PayoutStatus.QUEUED.value,
#         "message": "payout request queued for admin processing",
#     }


# # @router.post("/admin/process/{transfer_id}")
# # async def admin_process(transfer_id: str):
# #     payout = await PayoutTransaction.get_or_none(transfer_id=transfer_id)
# #     if not payout:
# #         raise HTTPException(status_code=404, detail="payout not found")
# #     await payout.fetch_related("vendor", "beneficiary")

# #     if payout.status != PayoutStatus.QUEUED:
# #         raise HTTPException(status_code=400, detail="payout not queued")
# #     transfer_amount = float(Decimal(payout.amount).quantize(Decimal("0.01")))

# #     body = {
# #         "transfer_id": payout.transfer_id,
# #         "transfer_amount": transfer_amount,
# #         "beneficiary_details": {
# #             "beneficiary_id": payout.beneficiary.beneficiary_id,
# #         },
# #         "transfer_mode": "banktransfer",
# #         "currency": "INR",
# #         "transfer_remarks": "Vendor automatic payout",
# #     }

# #     # call_cashfree_transfer might be sync or async; handle both
# #     if inspect.iscoroutinefunction(call_cashfree_transfer):
# #         status_code, cf_resp = await call_cashfree_transfer(body)
# #     else:
# #         # call in threadpool so we don't block the event loop if it's CPU-bound/blocking
# #         loop = asyncio.get_running_loop()
# #         status_code, cf_resp = await loop.run_in_executor(None, lambda: call_cashfree_transfer(body))

# #     # SUCCESS or ACCEPTED
# #     if status_code in (200, 201):
# #         cf_status_raw = (cf_resp.get("status") or "")
# #         cf_status = cf_status_raw.upper()

# #         async with in_transaction():
# #             payout.cf_response = cf_resp
# #             # compute paise as integer
# #             paise = int((Decimal(payout.amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_DOWN))
# #             payout.amount_in_paise = paise

# #             if cf_status in ("SUCCESS", "ACCEPTED"):
# #                 payout.status = PayoutStatus.SUCCESS
# #                 # reduce pending balance
# #                 ledger = await VendorAccount.get(vendor=payout.vendor)
# #                 ledger.pending_balance = (
# #                     Decimal(ledger.pending_balance) - Decimal(payout.amount)
# #                 ).quantize(Decimal("0.01"))
# #                 await ledger.save()

# #             elif cf_status in ("PENDING", "PROCESSING", "ACCEPTED_PARTIAL"):
# #                 payout.status = PayoutStatus.PROCESSING

# #             else:
# #                 payout.status = PayoutStatus.FAILED

# #             await payout.save()

# #         return {
# #             "ok": True,
# #             "cf_status": cf_status,
# #             "cf": cf_resp
# #         }

# #     # FAILURE: mark payout failed and refund amount back to withdrawable
# #     async with in_transaction():
# #         payout.status = PayoutStatus.FAILED
# #         payout.cf_response = cf_resp
# #         await payout.save()

# #         ledger = await VendorAccount.get(vendor=payout.vendor)
# #         ledger.pending_balance = (
# #             Decimal(ledger.pending_balance) - Decimal(payout.amount)
# #         ).quantize(Decimal("0.01"))
# #         ledger.withdrawable_balance = (
# #             Decimal(ledger.withdrawable_balance) + Decimal(payout.amount)
# #         ).quantize(Decimal("0.01"))
# #         await ledger.save()

# #     raise HTTPException(
# #         status_code=400,
# #         detail={
# #             "error": "cashfree transfer failed",
# #             "status_code": status_code,
# #             "cf_resp": cf_resp,
# #         },
# #     )
