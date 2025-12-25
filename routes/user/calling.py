import requests
from fastapi import APIRouter, HTTPException, Query
from app.config import settings

router = APIRouter(prefix="/call", tags=["Call Mask"])

EXOTEL_SID = settings.EXOTEL_SID
API_KEY = settings.EXOTEL_API_KEY
API_TOKEN = settings.EXOTEL_API_TOKEN
CALLER_ID = settings.EXOTEL_CALLER_ID

@router.post("/masked")
def make_masked_call(
    customer_number: str = Query(..., description="From number"),
    agent_number: str = Query(..., description="To number"),
    record: bool = Query(True, description="Whether to record the call")
):
    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"

    payload = {
        "From": customer_number,
        "To": agent_number,
        "CallerId": CALLER_ID,
        "Record": "true" if record else "false"
    }
    print("Calling Exotel with payload:", payload)

    try:
        response = requests.post(url, data=payload, auth=(API_KEY, API_TOKEN))
        response.raise_for_status()  # Raises HTTPError for bad responses
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Call initiated successfully",
        "exotel_response": response.json()
    }
