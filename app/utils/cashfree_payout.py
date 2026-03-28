import time
import base64
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from app.config import settings

CLIENT_ID = settings.CASHFREE_CLIENT_PAYOUT_ID
CLIENT_SECRET = settings.CASHFREE_CLIENT_PAYOUT_SECRET
CASHFREE_PUBLIC_KEY = settings.CASHFREE_PUBLIC_KEY
BASE_URL = settings.CASHFREE_BASE_URL or "https://sandbox.cashfree.com/payout"

def generate_signature_and_headers():
    timestamp = str(int(time.time()))
    sign_string = f"{CLIENT_ID}.{timestamp}".encode()

    public_key = serialization.load_pem_public_key(CASHFREE_PUBLIC_KEY.encode())
    encrypted = public_key.encrypt(
        sign_string,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
    )
    signature = base64.b64encode(encrypted).decode()

    headers = {
        "x-api-version": "2024-01-01",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
        "x-cf-signature": signature,
        "x-cf-timestamp": timestamp,
        "Content-Type": "application/json",
    }
    return headers

def call_cashfree_transfer(body: dict):
    url = f"{BASE_URL}/transfers"
    headers = generate_signature_and_headers()
    resp = requests.post(url, json=body, headers=headers, timeout=30)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {"raw": resp.text}
