from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from contextlib import asynccontextmanager
from tortoise.contrib.fastapi import register_tortoise
from .routes import create_sub_app
import importlib
from .utils import sync_permissions
from .config import settings
from pathlib import Path
from fastapi.staticfiles import StaticFiles


origins = [
    "http://localhost:3000",   
    "http://127.0.0.1:3000",
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # First: sync permissions
    await sync_permissions()

    # Second: create default superuser
    from applications.user.models import User
    admin_user = await User.filter(username="admin").first()
    if not admin_user:
        await User.create(
            username="admin",
            email="admin@gmail.com",
            password_hash=User.hash_password("admin"),
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        print("✅ Default superuser created: username=admin, password=admin")
    else:
        print("ℹ️ Default superuser already exists.")

    # Let FastAPI run
    yield

    # Optional: shutdown tasks here
    print("Application shutdown complete.")


app = FastAPI(lifespan=lifespan, debug=settings.DEBUG)

apps = ["user", "item", "auth"]

def get_model_modules(apps):
    modules = []
    for app_name in apps:
        module_path = Path(f"applications/{app_name}/models.py")
        if module_path.exists():
            modules.append(f"applications.{app_name}.models")
    return modules


register_tortoise(
    app,
    db_url=settings.DATABASE_URL,
    modules={"models": get_model_modules(apps)},
    generate_schemas=True,
    add_exception_handlers=True,
)


for app_name in apps:
    routes_module = importlib.import_module(f"applications.{app_name}.routes")
    sub_app = create_sub_app(app_name, routes_module.router)
    app.mount(f"/{app_name}", sub_app)
    
    

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,    
    allow_credentials=True,
    allow_methods=["*"],     
    allow_headers=["*"],     
)



app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")