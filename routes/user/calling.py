import requests
from fastapi import APIRouter, HTTPException
from app.config import settings
router = APIRouter(prefix='call', tags=['Call Mask'])

EXOTEL_SID = settings.EXOTEL_SID
API_KEY = settings.EXOTEL_API_KEY
API_TOKEN = settings.EXOTEL_API_TOKEN
CALLER_ID = settings.EXOTEL_CALLER_ID

@router.post("/masked")
def make_masked_call(customer_number: str, agent_number: str, record: bool = True):
    url = f"https://api.exotel.com/v1/Accounts/{settings.EXOTEL_SID}/Calls/connect.json"



    payload = {
        "From": customer_number,
        "To": agent_number,
        "CallerId": CALLER_ID,
        "Record": "true" if record else "false"
    }
    print(">>>>>>>>>>>>>>>>", payload)

    # response = requests.post(
    #     url,
    #     data=payload,
    #     auth=(API_KEY, API_TOKEN)
    # )
    response = requests.post(f'https://{settings.EXOTEL_API_KEY}:{settings.EXOTEL_API_TOKEN}api.exotel.com/v1/Accounts/{settings.EXOTEL_SID}/Calls/connect', data=payload)

    

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=response.text)

    return {
        "message": "Call initiated successfully",
        "exotel_response": response.json()
    }
