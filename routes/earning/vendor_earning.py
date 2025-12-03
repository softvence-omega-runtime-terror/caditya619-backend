# routers/payout.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, constr, condecimal
from applications.user.vendor import VendorProfile as Vendor
from applications.earning.vendor_earning import Beneficiary, VendorLedger, PayoutTransaction
from app.utils.cashfree_payout import generate_signature_and_headers, call_cashfree_transfer
from tortoise.transactions import in_transaction
import uuid
from decimal import Decimal

router = APIRouter(prefix="/payout", tags=["payout"])

class WithdrawRequest(BaseModel):
    vendor_id: int
    beneficiary_id: int
    amount: condecimal(gt=Decimal("0.99"))  # > 1.00 INR

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

    beneficiary = await Beneficiary.get_or_none(id=req.beneficiary_id, vendor=vendor, is_active=True)
    if not beneficiary:
        raise HTTPException(400, "beneficiary not found")

    transfer_id = f"txn_{uuid.uuid4().hex[:24]}"
    # create payout transaction queued
    async with in_transaction():
        await PayoutTransaction.create(
            vendor=vendor,
            beneficiary=beneficiary,
            transfer_id=transfer_id,
            amount=amount,
        )
        # move balance: hold funds
        ledger.withdrawable_balance = ledger.withdrawable_balance - amount
        ledger.pending_balance = ledger.pending_balance + amount
        await ledger.save()

    return {"transfer_id": transfer_id, "status": "queued"}

@router.post("/admin/process/{transfer_id}")
async def admin_process(transfer_id: str):
    """Admin endpoint to process a queued payout (or worker should call this)."""
    payout = await PayoutTransaction.get_or_none(transfer_id=transfer_id).prefetch_related("vendor", "beneficiary")
    if not payout:
        raise HTTPException(404, "payout not found")
    if payout.status != "queued":
        raise HTTPException(400, "payout not queued")

    # Build cashfree body
    body = {
        "transfer_id": payout.transfer_id,
        # cashfree expects transfer_amount in rupees (float) for v2
        "transfer_amount": float(payout.amount),
        "beneficiary_details": {
            "beneficiary_id": payout.beneficiary.beneficiary_id  # this is CF beneficiary id saved earlier
        },
        "transfer_mode": "banktransfer",
        "currency": "INR",
        "transfer_remarks": "Auto payout"
    }

    status_code, cf_resp = call_cashfree_transfer(body)

    # update record
    if status_code in (200, 201):
        # <- check CF response structure for actual success flag, adapt accordingly
        # many responses have {"status":"SUCCESS","..."}
        if (cf_resp.get("status") or "").upper() in ("SUCCESS", "ACCEPTED", "PENDING"):
            payout.status = "processing" if cf_resp.get("status").upper() == "PENDING" else "success"
            payout.cf_response = cf_resp
            payout.amount_in_paise = int(payout.amount * 100)
            await payout.save()
            # if success, move pending -> not pending and log
            async with in_transaction():
                ledger = await VendorLedger.get(vendor=payout.vendor)
                if payout.status == "success":
                    ledger.pending_balance = ledger.pending_balance - payout.amount
                    await ledger.save()
            return {"ok": True, "cf": cf_resp}
    # else failure
    payout.status = "failed"
    payout.cf_response = cf_resp
    await payout.save()
    # refund pending_balance -> withdrawable
    async with in_transaction():
        ledger = await VendorLedger.get(vendor=payout.vendor)
        ledger.pending_balance = max(Decimal(0), ledger.pending_balance - payout.amount)
        ledger.withdrawable_balance = ledger.withdrawable_balance + payout.amount
        await ledger.save()
    raise HTTPException(400, detail={"status_code": status_code, "cf_resp": cf_resp})
