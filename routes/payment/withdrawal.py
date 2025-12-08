import time
import hmac
import hashlib
import base64
import requests
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
import uuid
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from app.config import settings
from applications.user.rider import RiderProfile, Withdrawal, WorkDay,BeneficiaryAccount
from applications.user.models import User
from app.token import get_current_user
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# ============================================================================
# LOGGING SETUP
# ============================================================================
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
CLIENT_ID = settings.CASHFREE_CLIENT_PAYOUT_ID
CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYOUT_SECRET
PUBLIC_KEY = settings.CASHFREE_PUBLIC_KEY
BASE_URL = "https://sandbox.cashfree.com/payout"  # Change to production URL in .env

# Payout configuration
MINIMUM_WITHDRAWAL = Decimal("100.00")
MAXIMUM_WITHDRAWAL = Decimal("100000.00")
PROCESSING_FEE = Decimal("0.00")

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================
class WithdrawalStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ErrorType:
    INVALID_ACCOUNT = "invalid_account"  # Don't retry
    INSUFFICIENT_BALANCE = "insufficient_balance"  # Don't retry
    NETWORK_ERROR = "network_error"  # Retry
    API_ERROR = "api_error"  # Retry
    UNKNOWN = "unknown"  # Retry

# ============================================================================
# PYDANTIC MODELS (SCHEMAS)
# ============================================================================
class BeneficiaryCreate(BaseModel):
    """Add bank details to rider profile"""
    bank_account_number: str
    bank_ifsc: str
    bank_holder_name: str

    class Config:
        example = {
            "bank_account_number": "026291800001191",
            "bank_ifsc": "YESB0000262",
            "bank_holder_name": "Moynul Islam"
        }

class WithdrawalRequest(BaseModel):
    """Request withdrawal"""
    amount: Decimal = Field(..., gt=0)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        if v < MINIMUM_WITHDRAWAL or v > MAXIMUM_WITHDRAWAL:
            raise ValueError(f"Amount must be between {MINIMUM_WITHDRAWAL} and {MAXIMUM_WITHDRAWAL}")
        return v

    class Config:
        example = {
            "amount": 5000.00,
            "idempotency_key": "550e8400-e29b-41d4-a716-446655440000"
        }

class WithdrawalResponse(BaseModel):
    """Response for withdrawal"""
    id: UUID
    amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BeneficiaryDetails(BaseModel):
    """Get beneficiary details"""
    bank_account_number: str
    bank_ifsc: str
    bank_holder_name: str
    is_verified: bool

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def generate_signature():
    """Generate RSA-encrypted signature for Cashfree API"""
    try:
        timestamp = int(time.time())
        sign_string = f"{CLIENT_ID}.{timestamp}".encode()
        public_key = serialization.load_pem_public_key(PUBLIC_KEY.encode())
        encrypted = public_key.encrypt(
            sign_string,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            )
        )
        signature = base64.b64encode(encrypted).decode()
        return signature, str(timestamp)
    except Exception as e:
        logger.error(f"Error generating signature: {str(e)}")
        raise

def classify_error(status_code: int, response: dict) -> str:
    """Classify error type to determine if we should retry"""
    if status_code == 400:
        error_code = response.get("code", "")
        if "invalid" in error_code.lower() or "account" in error_code.lower():
            return ErrorType.INVALID_ACCOUNT
    elif status_code == 402:
        return ErrorType.INSUFFICIENT_BALANCE
    elif status_code in [500, 502, 503, 504]:
        return ErrorType.API_ERROR
    elif status_code >= 500:
        return ErrorType.API_ERROR
    return ErrorType.NETWORK_ERROR

# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(tags=["Withdrawals"])

# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/test/")
async def test():
    return {"message": "Hello World"}

@router.post("/beneficiary/add", status_code=201)
async def add_beneficiary(
    payload: BeneficiaryCreate,
    user: User = Depends(get_current_user)
):
    """
    Add or update bank details for rider
    This endpoint adds bank account details to the rider's profile.
    """
    rider = await RiderProfile.get(user=user)
    try:
        # 1. Verify rider is allowed to add beneficiary
        if not rider.is_verified:
            raise HTTPException(
                status_code=403,
                detail="Rider must be verified to add bank details"
            )

        # 2. Update rider profile with bank details
        # rider.bank_account_number = payload.bank_account_number
        # rider.bank_ifsc = payload.bank_ifsc
        # rider.bank_holder_name = payload.bank_holder_name
        # rider.is_bank_verified = False
        # await rider.save()
        beneficiary = await BeneficiaryAccount.create(
            rider = rider,
            bank_account_number = payload.bank_account_number,
            bank_ifsc = payload.bank_ifsc,
            bank_holder_name = payload.bank_holder_name,
            is_bank_verified = False
        )
        await beneficiary.save()

        logger.info(f"Bank details updated for rider {rider.id}")
        return {
            "success": True,
            "message": "Bank details saved successfully",
            "data": {
                "bank_account_number": f"****{payload.bank_account_number[-4:]}",
                "bank_ifsc": payload.bank_ifsc,
                "is_verified": beneficiary.is_bank_verified
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding beneficiary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save bank details")
    



@router.get("/beneficiary")
async def get_beneficiary(user: User = Depends(get_current_user)):
    """Get rider's bank details"""
    rider = await RiderProfile.get(user=user)
    beneficiary = await BeneficiaryAccount.filter(rider=rider)
    try:
        if not beneficiary:
            raise HTTPException(status_code=404, detail="No bank details found")
        
        return beneficiary
        
        # return {
        #     "bank_account_number": f"****{rider.bank_account_number[-4:]}",
        #     "bank_ifsc": rider.bank_ifsc,
        #     "bank_holder_name": rider.bank_holder_name,
        #     "is_verified": rider.is_bank_verified,
        #     "created_at": rider.updated_at
        # }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting beneficiary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch bank details")

@router.post("/request", status_code=202)
async def request_withdrawal(
    ben_id: int,
    payload: WithdrawalRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    """
    Request withdrawal (returns 202 Accepted, processes in background)
    """
    rider = await RiderProfile.get(user=user)
    beneficiary = await BeneficiaryAccount.get(id = ben_id)
    try:
        # 1. Validate rider has bank details
        if not beneficiary:
            raise HTTPException(
                status_code=400,
                detail="Please add bank details before requesting withdrawal"
            )

        # 2. Check balance
        if rider.current_balance < payload.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Available: ₹{rider.current_balance}"
            )

        # 3. Check for duplicate request (idempotency)
        existing = await Withdrawal.filter(
            rider=rider,
            status__in=[WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING]
        ).first()

        if existing:
            # Convert ORM object to dict manually to avoid validation errors
            existing_data = {
                "id": existing.id,
                "amount": existing.amount,
                "status": existing.status,
                "created_at": existing.created_at,
                "updated_at": existing.updated_at
            }
            return {
                "message": "Withdrawal already in progress",
                "data": existing_data
            }

        # 4. Create withdrawal record
        withdrawal = await Withdrawal.create(
            rider=rider,
            amount=payload.amount,
            status=WithdrawalStatus.PENDING,
            idempotency_key=payload.idempotency_key
        )

        # 5. Deduct from balance immediately (pessimistic)
        rider.current_balance -= payload.amount
        await rider.save()

        logger.info(f"Withdrawal {withdrawal.id} created for rider {rider.id}, amount: {payload.amount}")

        await process_withdrawal(withdrawal_id=str(withdrawal.id), rider_id=rider.id, beneficiary=beneficiary)

        # 6. Process in background
        # background_tasks.add_task(
        #     process_withdrawal,
        #     withdrawal_id=withdrawal.id,
        #     rider_id=rider.id
        # )

        return {
            "message": "Withdrawal request accepted. Processing...",
            "data": {
                "id": str(withdrawal.id),
                "amount": str(withdrawal.amount),
                "status": withdrawal.status,
                "created_at": withdrawal.created_at
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting withdrawal: {str(e)}")
        # Restore balance on error
        try:
            rider.current_balance += payload.amount
            await rider.save()
        except:
            pass
        raise HTTPException(status_code=500, detail="Failed to process withdrawal request")

@router.get("/{withdrawal_id}/status")
async def get_withdrawal_status(
    withdrawal_id: str,
    user: User = Depends(get_current_user)
):
    """Get withdrawal status"""
    rider = await RiderProfile.get(user=user)
    try:
        withdrawal = await Withdrawal.get_or_none(
            id=withdrawal_id,
            rider=rider
        )

        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal not found")

        return {
            "id": str(withdrawal.id),
            "amount": str(withdrawal.amount),
            "status": withdrawal.status,
            "created_at": withdrawal.created_at,
            "updated_at": withdrawal.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting withdrawal status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch status")

@router.get("/")
async def list_withdrawals(
    skip: int = 0,
    limit: int = 20,
    user: User = Depends(get_current_user)
):
    """List rider's withdrawals"""
    rider = await RiderProfile.get(user=user)
    try:
        withdrawals = await Withdrawal.filter(rider=rider).offset(skip).limit(limit)
        return {
            "count": len(withdrawals),
            "data": [
                {
                    "id": str(w.id),
                    "amount": str(w.amount),
                    "status": w.status,
                    "created_at": w.created_at
                }
                for w in withdrawals
            ]
        }
    except Exception as e:
        logger.error(f"Error listing withdrawals: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch withdrawals")

# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

async def process_withdrawal(withdrawal_id: str, rider_id: int, beneficiary: BeneficiaryAccount):
    """
    Process withdrawal in background
    """
    print("process_withdrawal")
    try:
        logger.info(f"Processing withdrawal {withdrawal_id}")
        
        # Get withdrawal and rider
        withdrawal = await Withdrawal.get(id=withdrawal_id)
        rider = await RiderProfile.get(id=rider_id)

        # Update status to processing
        withdrawal.status = WithdrawalStatus.PROCESSING
        await withdrawal.save()

        # Step 1: Add beneficiary (if not verified)
        if not beneficiary.is_bank_verified:
            logger.info(f"Adding beneficiary for rider {rider.id}")
            beneficiary_result = await add_beneficiary_to_cashfree(rider, beneficiary)
            print("beneficiary_result", beneficiary_result)
            if not beneficiary_result["success"]:
                await handle_withdrawal_error(
                    withdrawal, rider,
                    "Failed to add beneficiary",
                    ErrorType.INVALID_ACCOUNT
                )
                return
            beneficiary.is_bank_verified = True
            await beneficiary.save()

        # Step 2: Initiate transfer
        transfer_result = await transfer_amount_to_cashfree(
            withdrawal=withdrawal,
            rider=rider
        )

        if transfer_result["success"]:
            withdrawal.status = WithdrawalStatus.SUCCESS
            withdrawal.cashfree_transfer_id = transfer_result.get("transfer_id")
            await withdrawal.save()
            logger.info(f"Withdrawal {withdrawal_id} processed successfully")
        else:
            error_type = classify_error(
                transfer_result.get("status_code", 500),
                transfer_result.get("response", {})
            )
            await handle_withdrawal_error(
                withdrawal, rider,
                transfer_result.get("error", "Transfer failed"),
                error_type
            )
    except Exception as e:
        logger.error(f"Error processing withdrawal {withdrawal_id}: {str(e)}")
        try:
            withdrawal = await Withdrawal.get(id=withdrawal_id)
            await handle_withdrawal_error(
                withdrawal, None,
                str(e),
                ErrorType.UNKNOWN
            )
        except:
            pass

async def add_beneficiary_to_cashfree(rider: RiderProfile, beneficiary: BeneficiaryAccount) -> Dict[str, Any]:
    """Add beneficiary to Cashfree"""
    print("add_beneficiary_to_cashfree")
    try:
        signature, timestamp = generate_signature()
        url = f"{BASE_URL}/beneficiary"
        user = await User.get(id=rider.user_id)
        headers = {
            "x-api-version": "2024-01-01",
            "x-client-id": CLIENT_ID,
            "x-client-secret": CLIENT_SECRET,
            "x-cf-signature": signature,
            "x-cf-timestamp": timestamp,
            "Content-Type": "application/json",
        }

        body = {
            "beneficiary_id": f"rider_{rider.id}_{beneficiary.id}",
            "beneficiary_name": beneficiary.bank_holder_name,
            "beneficiary_instrument_details": {
                "bank_account_number": beneficiary.bank_account_number,
                "bank_ifsc": beneficiary.bank_ifsc,
            },
            "beneficiary_contact_details": {
                "beneficiary_email": user.email,
                "beneficiary_phone": user.phone,
                "beneficiary_country_code": "+91",
            },
        }

        logger.debug(f"Adding beneficiary with body: {body}")
        response = requests.post(url, json=body, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"Beneficiary added for rider {rider.id}")
            return {"success": True, "data": response.json()}
        else:
            logger.error(f"Failed to add beneficiary: {response.text}")
            return {"success": False, "error": response.text}
    except Exception as e:
        logger.error(f"Error adding beneficiary to Cashfree: {str(e)}")
        return {"success": False, "error": str(e)}

async def transfer_amount_to_cashfree(withdrawal, rider: RiderProfile) -> Dict[str, Any]:
    """Initiate transfer with Cashfree"""
    print("transfer_amount_to_cashfree")
    try:
        signature, timestamp = generate_signature()
        url = f"{BASE_URL}/transfers"
        headers = {
            "x-api-version": "2024-01-01",
            "x-client-id": CLIENT_ID,
            "x-client-secret": CLIENT_SECRET,
            "x-cf-signature": signature,
            "x-cf-timestamp": timestamp,
            "Content-Type": "application/json",
        }

        body = {
            "transfer_id": str(withdrawal.id),
            "transfer_amount": float(withdrawal.amount),
            "beneficiary_details": {
                "beneficiary_id": f"rider_{rider.id}"
            },
            "transfer_mode": "banktransfer",
            "currency": "INR",
            "transfer_remarks": f"Withdrawal for rider {rider.id}",
        }

        response = requests.post(url, json=body, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            result = response.json()
            logger.info(f"Transfer initiated for withdrawal {withdrawal.id}: {result}")
            return {
                "success": True,
                "transfer_id": result.get("transfer_id"),
                "data": result
            }
        else:
            logger.error(f"Transfer failed: {response.text}")
            return {
                "success": False,
                "status_code": response.status_code,
                "response": response.json() if response.text else {},
                "error": response.text
            }
    except Exception as e:
        logger.error(f"Error transferring amount: {str(e)}")
        return {
            "success": False,
            "status_code": 500,
            "error": str(e)
        }

async def handle_withdrawal_error(
    withdrawal,
    rider: Optional[RiderProfile],
    error_message: str,
    error_type: str
):
    """Handle withdrawal error and decide on retry"""
    print("handle_withdrawal_error")
    logger.error(f"Withdrawal {withdrawal.id} error: {error_message} ({error_type})")
    
    # Non-retryable errors
    if error_type in [ErrorType.INVALID_ACCOUNT, ErrorType.INSUFFICIENT_BALANCE]:
        withdrawal.status = WithdrawalStatus.FAILED
        withdrawal.error_message = error_message
        await withdrawal.save()

        # Restore balance
        if rider:
            rider.current_balance += withdrawal.amount
            await rider.save()
    # Retryable errors
    else:
        withdrawal.status = WithdrawalStatus.FAILED
        withdrawal.error_message = error_message
        await withdrawal.save()
        
        if rider:
            rider.current_balance += withdrawal.amount
            await rider.save()

        logger.warning(f"Withdrawal {withdrawal.id} marked as failed due to {error_type}")

# ============================================================================
# WEBHOOK ENDPOINT (Optional, for Cashfree callbacks)
# ============================================================================

@router.post("/webhook/cashfree")
async def handle_cashfree_webhook(request: dict):
    """
    Handle Cashfree webhook callbacks
    Cashfree will call this endpoint when transfer status changes
    """
    try:
        # Extract transfer_id and status
        transfer_id = request.get("transfer_id")
        status = request.get("status")
        logger.info(f"Webhook received for transfer {transfer_id}, status: {status}")

        # Get withdrawal
        withdrawal = await Withdrawal.get_or_none(id=transfer_id)
        if not withdrawal:
            logger.warning(f"Withdrawal {transfer_id} not found")
            return {"success": False, "error": "Withdrawal not found"}

        # Update status based on Cashfree response
        status_map = {
            "SUCCESS": WithdrawalStatus.SUCCESS,
            "FAILED": WithdrawalStatus.FAILED,
            "PROCESSING": WithdrawalStatus.PROCESSING,
        }

        withdrawal.status = status_map.get(status, WithdrawalStatus.FAILED)
        await withdrawal.save()

        logger.info(f"Withdrawal {transfer_id} updated to {withdrawal.status}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        return {"success": False, "error": str(e)}