# routers/payout.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, condecimal
from tortoise.transactions import in_transaction
from decimal import Decimal
import uuid

from applications.user.vendor import VendorProfile as Vendor
from applications.earning.vendor_earning import (
    Beneficiary,
    VendorLedger,
    PayoutTransaction
)

from app.utils.cashfree_payout import (
    generate_signature_and_headers,
    call_cashfree_transfer
)

router = APIRouter(prefix="/payout", tags=["payout"])


# -----------------------------
#  REQUEST WITHDRAW
# -----------------------------
class WithdrawRequest(BaseModel):
    vendor_id: int
    beneficiary_id: int
    amount: condecimal(gt=Decimal("0.99"))  # Minimum 1.00 INR


@router.post("/request_withdraw")
async def request_withdraw(req: WithdrawRequest):

    vendor = await Vendor.get_or_none(id=req.vendor_id)
    if not vendor:
        raise HTTPException(404, "vendor not found")

    ledger = await VendorLedger.get_or_none(vendor=vendor)
    if not ledger:
        raise HTTPException(400, "ledger missing")

    amount = Decimal(req.amount)

    if ledger.withdrawable_balance < amount:
        raise HTTPException(400, "insufficient withdrawable balance")

    beneficiary = await Beneficiary.get_or_none(
        id=req.beneficiary_id, vendor=vendor, is_active=True
    )
    if not beneficiary:
        raise HTTPException(400, "beneficiary not found")

    # unique transfer id for CF
    transfer_id = f"txn_{uuid.uuid4().hex[:24]}"

    # create transaction + move withdrawable → pending
    async with in_transaction():
        await PayoutTransaction.create(
            vendor=vendor,
            beneficiary=beneficiary,
            transfer_id=transfer_id,
            amount=amount,
            status="queued",
        )

        ledger.withdrawable_balance -= amount
        ledger.pending_balance += amount
        await ledger.save()

    return {
        "transfer_id": transfer_id,
        "status": "queued",
        "message": "payout request queued for admin processing",
    }


# -----------------------------
#  ADMIN / WORKER PROCESS
# -----------------------------
@router.post("/admin/process/{transfer_id}")
async def admin_process(transfer_id: str):

    payout = (
        await PayoutTransaction
        .get_or_none(transfer_id=transfer_id)
        .prefetch_related("vendor", "beneficiary")
    )

    if not payout:
        raise HTTPException(404, "payout not found")

    if payout.status != "queued":
        raise HTTPException(400, "payout not queued")

    # Convert to paise if required
    transfer_amount = float(payout.amount)

    # Build Cashfree body
    body = {
        "transfer_id": payout.transfer_id,
        "transfer_amount": transfer_amount,
        "beneficiary_details": {
            "beneficiary_id": payout.beneficiary.beneficiary_id,
        },
        "transfer_mode": "banktransfer",
        "currency": "INR",
        "transfer_remarks": "Vendor automatic payout",
    }

    status_code, cf_resp = call_cashfree_transfer(body)

    # -------------------------
    # SUCCESS OR ACCEPTED
    # -------------------------
    if status_code in (200, 201):
        cf_status = (cf_resp.get("status") or "").upper()
        async with in_transaction():
            payout.cf_response = cf_resp
            payout.amount_in_paise = int(payout.amount * 100)

            if cf_status in ("SUCCESS", "ACCEPTED"):
                payout.status = "success"

                ledger = await VendorLedger.get(vendor=payout.vendor)
                ledger.pending_balance -= payout.amount
                await ledger.save()

            elif cf_status in ("PENDING", "PROCESSING"):
                payout.status = "processing"

            else:
                payout.status = "failed"

            await payout.save()

        return {
            "ok": True,
            "cf_status": cf_status,
            "cf": cf_resp
        }

    # -------------------------
    # FAILURE: REFUND AMOUNT
    # -------------------------
    async with in_transaction():

        payout.status = "failed"
        payout.cf_response = cf_resp
        await payout.save()

        ledger = await VendorLedger.get(vendor=payout.vendor)
        ledger.pending_balance -= payout.amount
        ledger.withdrawable_balance += payout.amount
        await ledger.save()

    raise HTTPException(
        400,
        detail={
            "error": "cashfree transfer failed",
            "status_code": status_code,
            "cf_resp": cf_resp,
        },
    )
