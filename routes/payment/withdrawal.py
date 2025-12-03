# routes/withdrawals.py
import os
import uuid
import decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx
from datetime import datetime
from fastapi.responses import JSONResponse
import base64

from tortoise.transactions import in_transaction
try:
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

# Import your Tortoise models
from applications.user.rider import RiderProfile, Withdrawal  # adjust import to your project
from app.token import get_current_user  # adjust according to your auth
from applications.user.models import User



from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider Withdrawal'])

# Config (read from env)
CASHFREE_CLIENT_ID="CF10898143D4L8U3J9JJ6C7392MESG"
CASHFREE_CLIENT_SECRET="cfsk_ma_test_f5f0e8ab9488e7b93ac49303e203dc24_fd14c175"
CASHFREE_API_VERSION="2024-01-01"
CASHFREE_BASE_URL="https://sandbox.cashfree.com/payout"

if not CASHFREE_CLIENT_ID or not CASHFREE_CLIENT_SECRET:
    # In dev it's helpful to raise early
    raise RuntimeError("Set CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET in env")

HEADERS = {
    "x-api-version": CASHFREE_API_VERSION,
    "x-client-id": CASHFREE_CLIENT_ID,
    "x-client-secret": CASHFREE_CLIENT_SECRET,
    "Content-Type": "application/json",
}


async def _create_beneficiary_if_not_exists(rider: RiderProfile) -> str:
    """
    Create (or reuse) a beneficiary id in Cashfree for a rider.
    Returns beneficiary_id (string).
    """
    # Choose a safe beneficiary_id scheme
    beneficiary_id = f"rider_{rider.id}"

    payload = {
        "beneficiary_id": beneficiary_id,
        "beneficiary_name": rider.bank_holder_name or f"Rider {rider.id}",
        "beneficiary_instrument_details": {
            "bank_account_number": rider.bank_account_number,
            "bank_ifsc": rider.bank_ifsc
        },
        "beneficiary_contact_details": {
            # optional: include phone/email if available
            "beneficiary_phone": getattr(rider, "phone", None) or "",
            "beneficiary_email": getattr(rider, "email", None) or "",
            "beneficiary_country_code": "+91"
        }
    }

    url = f"{CASHFREE_BASE_URL}/beneficiary"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=HEADERS)
        # 201 - created; 409 - already exists; other codes -> error
        if resp.status_code in (200, 201):
            return beneficiary_id
        elif resp.status_code == 409:
            # beneficiary exists — still return our beneficiary_id
            return beneficiary_id
        else:
            # bubble up error details for debugging
            raise HTTPException(status_code=502, detail={
                "msg": "failed to create beneficiary",
                "status": resp.status_code,
                "body": resp.text
            })


async def _create_transfer(beneficiary_id: str, transfer_id: str, amount: decimal.Decimal) -> dict:
    """
    Start a transfer (v2 transfers). Returns response JSON.
    amount is expected in rupees (decimal) - docs expect numeric (no paise multiplier required).
    """
    url = f"{CASHFREE_BASE_URL}/transfers"
    payload = {
        "transfer_id": transfer_id,
        "transfer_amount": float(amount),  # Cashfree expects number
        "beneficiary_details": {"beneficiary_id": beneficiary_id},
        # optional: "transfer_mode": "BANK"
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=HEADERS)
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            raise HTTPException(status_code=502, detail={
                "msg": "failed to create transfer",
                "status": resp.status_code,
                "body": resp.text
            })


async def _get_transfer_status(transfer_id: Optional[str] = None, cf_transfer_id: Optional[str] = None) -> dict:
    """
    Query Cashfree get-transfer-status V2.
    You can call GET /payout/transfers with query params or body depending on API. We'll call the generic GET and pass transfer_id as a query param.
    """
    url = f"{CASHFREE_BASE_URL}/transfers"
    params = {}
    if transfer_id:
        params["transfer_id"] = transfer_id
    if cf_transfer_id:
        params["cf_transfer_id"] = cf_transfer_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=HEADERS, params=params)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise HTTPException(status_code=502, detail={
                "msg": "failed to fetch transfer status",
                "status": resp.status_code,
                "body": resp.text
            })


async def _verify_signature(raw_body: bytes, signature_b64: str) -> None:
    """
    Verifies signature using CASHFREE_PUBLIC_KEY_PEM env var.
    Raises Exception on verification failure.
    """
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography not installed for signature verification")

    pub_pem = os.getenv("CASHFREE_PUBLIC_KEY_PEM")
    if not pub_pem:
        raise RuntimeError("No public key configured in CASHFREE_PUBLIC_KEY_PEM")

    sig_bytes = base64.b64decode(signature_b64)
    pubkey = serialization.load_pem_public_key(pub_pem.encode())
    # Cashfree signs raw body with RSA-SHA256 (this is typical). If they use different scheme adjust accordingly.
    pubkey.verify(
        sig_bytes,
        raw_body,
        padding.PKCS1v15(),
        hashes.SHA256()
    )




@router.post("/withdraw/", status_code=status.HTTP_201_CREATED)
async def request_withdrawal(amount: float, user: User = Depends(get_current_user)):
    """
    Rider requests a withdrawal. This will:
      - validate rider/bank details and available balance,
      - create Withdrawal row with status 'pending',
      - create beneficiary in Cashfree (if not exists),
      - create transfer in Cashfree and update Withdrawal record.
    """
    # fetch rider profile
    rider = await RiderProfile.get_or_none(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    # validations
    if not rider.bank_account_number or not rider.bank_ifsc or not rider.bank_holder_name:
        raise HTTPException(status_code=400, detail="Missing bank details, cannot withdraw")

    if decimal.Decimal(amount) <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    if rider.current_balance < decimal.Decimal(amount):
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # transaction: create withdrawal row and try to call Cashfree
    async with in_transaction() as conn:
        withdrawal = await Withdrawal.create(
            rider=rider,
            amount=decimal.Decimal(amount),
            status="pending",
            created_at=datetime.utcnow()
        )

        # create beneficiary
        try:
            beneficiary_id = await _create_beneficiary_if_not_exists(rider)
        except HTTPException as e:
            # update withdrawal status to failed
            withdrawal.status = "failed"
            withdrawal.remark = f"beneficiary error: {e.detail}"
            await withdrawal.save()
            raise

        # create unique transfer id
        transfer_id = f"wd_{withdrawal.id}"

        try:
            transfer_resp = await _create_transfer(beneficiary_id, transfer_id, decimal.Decimal(amount))
        except HTTPException as e:
            withdrawal.status = "failed"
            withdrawal.remark = f"transfer error: {e.detail}"
            await withdrawal.save()
            raise

        # On success, update withdrawal with reference
        # Cashfree may provide cf_transfer_id or transfer_id in response
        cf_transfer_id = transfer_resp.get("cf_transfer_id") or transfer_resp.get("data", {}).get("cf_transfer_id")
        withdrawal.cashfree_transfer_id = cf_transfer_id or transfer_resp.get("transfer_id") or transfer_id
        withdrawal.status = "processing"  # or 'initiated'
        await withdrawal.save()

        # optional: deduct immediately (business choice). Here we hold balance until success:
        # rider.current_balance -= decimal.Decimal(amount)
        # await rider.save()

    return {
        "status": "processing",
        "withdrawal_id": str(withdrawal.id),
        "transfer_id": transfer_id,
        "cashfree_transfer_id": withdrawal.cashfree_transfer_id,
        "amount": float(withdrawal.amount)
    }


@router.get("/withdrawals/{withdrawal_id}/status/")
async def withdrawal_status(withdrawal_id: str, user: User = Depends(get_current_user)):
    # get withdrawal
    w = await Withdrawal.get_or_none(id=withdrawal_id).prefetch_related("rider")
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    # check ownership
    if w.rider.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # query cashfree if we have a transfer id
    if not w.cashfree_transfer_id:
        return {"status": w.status, "detail": "No external transfer id"}

    status_resp = await _get_transfer_status(transfer_id=w.cashfree_transfer_id)
    return {"local_status": w.status, "cashfree_status": status_resp}


# Webhook endpoint skeleton
@router.post("/withdrawals/webhook/")
async def cashfree_webhook(request: Request):
    # Read raw body bytes
    raw = await request.body()
    headers = dict(request.headers)

    # Debug logs (remove or change to logger in prod)
    print("WEBHOOK HEADERS:", headers)
    print("WEBHOOK RAW LENGTH:", len(raw))

    if not raw or raw.strip() == b"":
        # Empty payload — respond with 400 to indicate misconfigured webhook sender
        return JSONResponse({"ok": False, "reason": "Empty request body"}, status_code=400)

    # Try parsing JSON first
    payload = None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Try form-encoded parsing
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            # Fallback: parse as urlencoded string
            try:
                text = raw.decode("utf-8", errors="ignore")
                from urllib.parse import parse_qs
                parsed = parse_qs(text)
                payload = {k: v[0] if v and isinstance(v, list) else v for k, v in parsed.items()}
            except Exception:
                payload = None

    if payload is None:
        return JSONResponse({"ok": False, "reason": "Unable to parse body (not JSON or form-data)"}, status_code=400)

    # Optional signature verification (recommended for production)
    sig = request.headers.get("x-cf-signature") or request.headers.get("X-Cf-Signature")
    if sig:
        try:
            await _verify_signature(raw, sig)
        except Exception as e:
            # signature failed
            return JSONResponse({"ok": False, "reason": "signature verification failed", "error": str(e)}, status_code=400)

    # Now handle payload fields. Cashfree may use cf_transfer_id, transfer_id, status, etc.
    transfer_id = payload.get("transfer_id") or payload.get("cf_transfer_id") or payload.get("data", {}).get("transfer_id") or payload.get("data", {}).get("cf_transfer_id")
    status_str = payload.get("status") or payload.get("data", {}).get("status") or payload.get("transfer_status")

    if not transfer_id:
        # try other helpful keys if needed
        return JSONResponse({"ok": False, "reason": "no transfer id in payload", "payload": payload}, status_code=400)

    # Find matching withdrawal - try both cashfree_transfer_id and transfer_id fields
    w = await Withdrawal.get_or_none(cashfree_transfer_id=transfer_id)
    if not w:
        # maybe stored transfer id is different; attempt search by transfer_id substring
        w = await Withdrawal.get_or_none(cashfree_transfer_id__icontains=transfer_id)

    if not w:
        # Not found — return 404 so sender knows we didn't match
        return JSONResponse({"ok": False, "reason": "withdrawal not found", "transfer_id": transfer_id}, status_code=404)

    # Map statuses from Cashfree to local statuses
    # Adjust mapping as per actual Cashfree status values you receive
    mapping = {
        "SUCCESS": "success",
        "COMPLETED": "success",
        "FAILED": "failed",
        "REVERSED": "failed",
        "PENDING": "processing",
        "PROCESSING": "processing"
    }

    new_status = None
    if status_str:
        new_status = mapping.get(status_str.upper(), status_str.lower())
    else:
        # fallback: try to read from payload.data
        ds = payload.get("data", {})
        new_status = mapping.get(ds.get("status", "").upper(), ds.get("status", None))

    # persist update inside transaction
    async with in_transaction():
        if new_status:
            w.status = new_status
        # optionally store raw payload / remark for audit
        try:
            # if model has remark field or an extra json field, save the payload summary
            if hasattr(w, "remark"):
                w.remark = json.dumps(payload)[:2000]  # avoid very long
        except Exception:
            pass
        await w.save()

    return JSONResponse({"ok": True, "withdrawal_id": str(w.id), "new_status": w.status})
