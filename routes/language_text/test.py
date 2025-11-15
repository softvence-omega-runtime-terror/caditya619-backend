from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.utils.translator import translate

router = APIRouter(prefix='/lang', tags=['Language'])

@router.get("/greet")
async def greet(request: Request):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    
    message = {
        "slug": "sdfsfsfsdfwrwe",
        "message": translate("Hello, welcome to our platform!", lang),
        "info": "This is a sample message."
    }
    
    return JSONResponse(content=message)
