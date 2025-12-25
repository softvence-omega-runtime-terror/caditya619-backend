# import requests
# from fastapi import APIRouter, HTTPException, Query
# from app.config import settings
#
# router = APIRouter(prefix="/call", tags=["Call Mask"])
#
# EXOTEL_SID = settings.EXOTEL_SID
# API_KEY = settings.EXOTEL_API_KEY
# API_TOKEN = settings.EXOTEL_API_TOKEN
# CALLER_ID = settings.EXOTEL_CALLER_ID
#
# @router.post("/masked")
# def make_masked_call(
#     customer_number: str = Query(..., description="From number"),
#     agent_number: str = Query(..., description="To number"),
#     record: bool = Query(True, description="Whether to record the call")
# ):
#     url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
#
#     payload = {
#         "From": customer_number,
#         "To": agent_number,
#         "CallerId": CALLER_ID,
#         "Record": "true" if record else "false"
#     }
#     print("Calling Exotel with payload:", payload)
#
#     try:
#         response = requests.post(url, data=payload, auth=(API_KEY, API_TOKEN))
#         response.raise_for_status()  # Raises HTTPError for bad responses
#     except requests.exceptions.RequestException as e:
#         raise HTTPException(status_code=400, detail=str(e))
#
#     return {
#         "message": "Call initiated successfully",
#         "exotel_response": response.json()
#     }


import re
import requests
from fastapi import APIRouter, HTTPException, Query
from app.config import settings

router = APIRouter(prefix="/call", tags=["Call Mask"])

EXOTEL_SID = settings.EXOTEL_SID
API_KEY = settings.EXOTEL_API_KEY
API_TOKEN = settings.EXOTEL_API_TOKEN
CALLER_ID = settings.EXOTEL_CALLER_ID

# Simple phone number validation (local format)
def validate_phone(number: str):
    pattern = re.compile(r'^\d{10,15}$')
    if not pattern.match(number):
        raise HTTPException(status_code=400, detail=f"Invalid phone number: {number}")

@router.post("/masked")
def make_masked_call(
    customer_number: str = Query(..., description="Customer's phone number"),
    agent_number: str = Query(..., description="Agent's phone number"),
    record: bool = Query(True, description="Whether to record the call"),
    status_callback: str = Query(
        None, description="Optional callback URL to receive call updates"
    ),
):
    # Validate numbers
    validate_phone(customer_number)
    validate_phone(agent_number)

    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"

    payload = {
        "From": customer_number,
        "To": agent_number,
        "CallerId": CALLER_ID,
        "Record": "true" if record else "false"
    }

    # Add status callback if provided
    if status_callback:
        payload["StatusCallback"] = status_callback
        payload["StatusCallbackEvents[0]"] = "terminal"  # only call termination
        payload["StatusCallbackContentType"] = "application/json"

    try:
        response = requests.post(url, data=payload, auth=(API_KEY, API_TOKEN))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Exotel API Error: {e}")

    return {
        "message": "Call initiated successfully",
        "exotel_response": response.json()
    }