from typing import Optional
from pydantic_settings import BaseSettings
from tortoise import Tortoise
import os

DATABASE_URL="postgres://neondb_owner:npg_zwcn6Qk1blht@ep-dark-fire-adgbt70y-pooler.c-2.us-east-1.aws.neon.tech/neondb"

class Settings(BaseSettings):
    DEBUG: bool = False
    ENV: str = "development"
    DATABASE_URL: str = DATABASE_URL 
    SECRET_KEY: Optional[str] = "c6dcf58058a6ce5204199818a25eed7eb58b6758a20df0385e29dbea6b49873dccad7449f8022dc193da4616ba10c97457aa2e16e0b2c5b0e5555fe1ac492aa1"

    class Config:
        env_file = None
                
settings = Settings()




TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": ["applications.user.models", "aerich.models"],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": "UTC",
}

async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    if os.environ.get("ENV") != "production":
        await Tortoise.generate_schemas()
