from typing import Optional
from pydantic_settings import BaseSettings
from tortoise import Tortoise
from app.utils.auto_routing import get_apps_structure


class Settings(BaseSettings):
    DEBUG: bool = True
    APP_NAME: str = "FastAPI App"
    MEDIA_DIR: str = "media/"
    MEDIA_ROOT: str = "media/"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite://db.sqlite3"
    TWOFACTOR_API_KEY: str = "f1972b11-9a1c-11f0-b922-0200cd936042"
    SECRET_KEY: Optional[str] = None
    BASE_URL: str = "http://localhost:8000/"
    RADIS_URL: str = "redis://localhost:6379/0"
    CASHFREE_CLIENT_PAYMENT_ID: str = ""
    CASHFREE_CLIENT_PAYMENT_SECRET: str = ""
    CASHFREE_CLIENT_PAYOUT_ID: str = ""
    CASHFREE_CLIENT_PAYOUT_SECRET: str = ""
    CASHFREE_ENV: str = "PRODUCTION"
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

TORTOISE_ORM = {
    "connections": {
        "default": settings.DATABASE_URL,
    },
    "apps": get_apps_structure("applications"),
    "use_tz": True,
    "timezone": "Asia/Dhaka",
}
import json
print(json.dumps(TORTOISE_ORM, indent=4))

async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    if settings.ENV != "production":
        await Tortoise.generate_schemas()
    else:
        print("Skipping schema generation in production.")


async def close_db():
    await Tortoise.close_connections()
