from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DEBUG: bool = False
    ENV: str = "development"
    POSTGRES_URL: str = "postgres://neondb_owner:npg_kY0Qo2RUXZVL@ep-damp-scene-adfwy4vs-pooler.c-2.us-east-1.aws.neon.tech/neondb"
    # DATABASE_URL=mysql://root:root@localhost:3306/mydb
    SECRET_KEY: Optional[str] = "c6dcf58058a6ce5204199818a25eed7eb58b6758a20df0385e29dbea6b49873dccad7449f8022dc193da4616ba10c97457aa2e16e0b2c5b0e5555fe1ac492aa1"

    class Config:
        env_file = ".env" 
        env_file_encoding = "utf-8"

settings = Settings()

print("POSTGRES_URL", settings.POSTGRES_URL)
TORTOISE_ORM = {
    "connections": {
        "default": settings.POSTGRES_URL or "sqlite://db.sqlite3"   # fallback
    },
    "apps": {
        "models": {
            "models": ["applications.user.models", "aerich.models"],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": "UTC",
}

