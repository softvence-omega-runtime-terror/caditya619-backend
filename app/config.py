from typing import Optional
from pydantic_settings import BaseSettings
from tortoise import Tortoise
import os

class Settings(BaseSettings):
    DEBUG: bool = True
    ENV: str = "development"
    DATABASE_URL: str
    SECRET_KEY: Optional[str]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
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
