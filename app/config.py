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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

apps_config = get_apps_structure("applications")
import json

print(json.dumps(apps_config, indent=4))

TORTOISE_ORM = {
    "connections": {
        "default": settings.DATABASE_URL,
    },
    "apps": apps_config | {
        "aerich": {
            "models": ["aerich.models"],
        },
    },
    "use_tz": True,
    "timezone": "Asia/Dhaka",
}


async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    if settings.ENV != "production":
        await Tortoise.generate_schemas()
    else:
        print("Skipping schema generation in production.")
