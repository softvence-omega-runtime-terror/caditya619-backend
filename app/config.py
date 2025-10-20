from typing import Optional, List, Dict
from pydantic_settings import BaseSettings
from tortoise import Tortoise
from app.utils.auto_routing import get_module
from pathlib import Path



class Settings(BaseSettings):
    DEBUG: bool = True
    APP_NAME: str = "FastAPI App"
    MEDIA_DIR: str = "media/"
    MEDIA_ROOT: str = "media/"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite://db.sqlite3"
    SECRET_KEY: Optional[str] = None
    BASE_URL: str = "http://localhost:8000/"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()


apps = get_module(base_dir='applications')

def get_model_modules(apps: List[str]) -> Dict[str, dict]:
    app_configs = {}
    for app_name in apps:
        module_path = Path(f"applications/{app_name}/models.py")
        if module_path.exists():
            app_configs[app_name] = {
                "models": [f"applications.{app_name}.models"],
                "default_connection": "default",
            }
    return app_configs

TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": get_model_modules(apps) | {"aerich": {"models": ["aerich.models"]}},
    "use_tz": True,
    "timezone": "Asia/Dhaka",
}

print("TORTOISE_ORM Configured:")
for app_label, app_config in TORTOISE_ORM["apps"].items():
    print(f"\n📦 App Label: {app_label}")
    print(f"  🗂 Models:")
    for model in app_config["models"]:
        print(f"    - {model}")
    if "default_connection" in app_config:
        print(f"  🔗 Connection: {app_config['default_connection']}")

# ✅ Initialize database connection
async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    if settings.ENV != "production":
        await Tortoise.generate_schemas()
    else:
        print("Skipping schema generation in production.")
