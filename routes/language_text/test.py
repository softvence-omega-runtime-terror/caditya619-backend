from fastapi import APIRouter, Request

router = APIRouter(prefix='/lang', tags=['Language'])

from deep_translator import GoogleTranslator
from typing import Any
from fastapi.responses import JSONResponse

def translate(obj: Any, target_lang: str) -> Any:
    if isinstance(obj, str):
        try:
            return GoogleTranslator(source='auto', target=target_lang).translate(obj)
        except Exception:
            return obj  # fallback if translation fails
    elif isinstance(obj, list):
        return [translate(item, target_lang) for item in obj]
    elif isinstance(obj, dict):
        return {k: translate(v, target_lang) for k, v in obj.items()}
    else:
        return obj


@router.get("/greet")
async def greet(request: Request):
    response_data = {
        "message": "Hello, welcome to our platform!",
        "info": "This is a sample message."
    }
    
    lang = request.headers.get("accept-language", "bn").split(",")[0].strip().lower() or "bn"
    
    translated = translate(response_data, "bn")
    
    return JSONResponse(content=translated)