from fastapi import HTTPException, status
import re


async def phone_number(value: str) -> str:
    value = value.strip()
    if value.startswith("91") and not value.startswith("+"):
        value = f"+{value}"
    elif value.startswith("0"):
        value = "+91" + value[1:]
    phone_regex = r'^\+91[6-9]\d{9}$'

    if re.match(phone_regex, value):
        return value 
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Please enter a correct phone number.'
        )