import requests
from pathlib import Path
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, asymmetric, hashes
import base64

# ----------------------------
# Load Cashfree Public Key
# ----------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent
PUBLIC_KEY_PATH = PROJECT_ROOT / "cashfree_public_key.pem"

print(f"Using public key at: {PUBLIC_KEY_PATH}")

with open(PUBLIC_KEY_PATH, "rb") as f:
    CASHFREE_PUBLIC_KEY = serialization.load_pem_public_key(f.read(), backend=default_backend())


# ----------------------------
# Encrypt OTP
# ----------------------------
def encrypt_otp(otp: str) -> str:
    """
    Encrypt the OTP using Cashfree public key.
    Returns base64 encoded string for API request.
    """
    encrypted = CASHFREE_PUBLIC_KEY.encrypt(
        otp.encode(),
        asymmetric.padding.OAEP(
            mgf=asymmetric.padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.b64encode(encrypted).decode()


# ----------------------------
# Authorize OTP
# ----------------------------
def authorize_payout(client_id: str, client_secret: str):
    url = "https://payout-gamma.cashfree.com/payout/v1/authorize"
    headers = {
        "X-Cf-Signature": encrypt_otp,
        "X-Client-Id": client_id,
        "X-Client-Secret": client_secret
    }

    resp = requests.post(url, headers=headers)

    try:
        resp.raise_for_status()
    except requests.HTTPError:
        # Return Cashfree error response if signature fails or any other error
        return resp.json()

    return resp.json()


# ----------------------------
# Trigger Payout
# ----------------------------
def trigger_payout(client_id: str, client_secret: str, payout_data: dict):
    """
    Trigger payout request after successful authorization.
    payout_data example:
    {
        "beneId": "123",
        "amount": "100",
        "currency": "INR",
        "mode": "NEFT",
        "purpose": "Salary"
    }
    """
    url = "https://payout-gamma.cashfree.com/payout/v1/request"  # correct endpoint
    headers = {
        "X-Client-Id": client_id,
        "X-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json=payout_data)

    try:
        resp.raise_for_status()
    except requests.HTTPError:
        return resp.json()

    return resp.json()
