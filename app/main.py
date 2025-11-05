import os
import importlib
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import settings, init_db
from app.redis import init_redis, redis_client
from app.routes import register_routes
from app.utils.sync_permissions import sync_permissions
from applications.user.models import User
from app.utils.auto_routing import get_module
from app.config import settings
from app.dummy.users import create_test_users

# import logging
# logging.basicConfig(level=logging.DEBUG)

@asynccontextmanager
async def lifespan(routerAPI: FastAPI):
    await init_db()
    init_redis()
    await sync_permissions()

    if settings.DEBUG:
        await create_test_users()
    
    for app_name in get_module(base_dir="applications"):
        try:
            importlib.import_module(f"applications.{app_name}.signals")
        except ModuleNotFoundError:
            print(f"⚠️ Warning: No signals.py in '{app_name}' sub-app.")
    yield
    if redis_client:
        await redis_client.aclose()
    print("Application shutdown complete.")


app = FastAPI(lifespan=lifespan, debug=settings.DEBUG)
register_routes(app)



from fastapi.responses import JSONResponse
from deep_translator import GoogleTranslator
import json

@app.middleware("http")
async def translate_response_middleware(request: Request, call_next):
    # Get primary language from header, default to 'bn'
    lang_header = request.headers.get("accept-language", "fr")
    lang = lang_header.split(",")[0].strip().lower()

    response = await call_next(request)

    # Only translate JSON responses
    if "application/json" in response.headers.get("content-type", ""):
        try:
            # Extract JSON data safely
            if hasattr(response, "body"):
                data = json.loads(response.body.decode())
            else:
                return response

            # Recursive translation
            def translate_data(obj):
                if isinstance(obj, str):
                    try:
                        return GoogleTranslator(source='auto', target=lang).translate(obj)
                    except Exception:
                        return obj
                elif isinstance(obj, list):
                    return [translate_data(item) for item in obj]
                elif isinstance(obj, dict):
                    return {k: translate_data(v) for k, v in obj.items()}
                return obj

            translated_data = translate_data(data)
            return JSONResponse(content=translated_data, status_code=response.status_code)

        except Exception as e:
            # If translation fails, return original response
            print("Translation middleware error:", e)
            return response

    return response



@app.get("/greet")
async def greet():
    return {"message": "Hello, welcome to our platform!", "info": "This is a sample message."}

@app.get("/farewell")
async def farewell():
    return {"message": "Goodbye! See you soon."}

templates = Jinja2Templates(directory="templates")
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    routes = get_module()
    html_file = "development.html" if settings.DEBUG else "index.html"
    return templates.TemplateResponse(
        html_file,
        {
            "request": request, 
            "routes": routes
        }
    )


ALLOWED_HOST = ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")
