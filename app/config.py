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
    FRONTEND_URL: str = ""
    BACKEND_URL: str = ""
    CASHFREE_CLIENT_PAYMENT_ID: str = ""
    CASHFREE_CLIENT_PAYMENT_SECRET: str = ""
    CASHFREE_CLIENT_PAYOUT_ID: str = ""
    CASHFREE_CLIENT_PAYOUT_SECRET: str = ""
    CASHFREE_ENV: str = "PRODUCTION"
    CASHFREE_PUBLIC_KEY: str = ""
    CASHFREE_BASE_URL: str = ""
    EXOTEL_SID: str = 'quikle1'
    EXOTEL_API_KEY: str = '94b292e4033d9fe63cc3b09baf99c4903a222d1ad2a529bd'
    EXOTEL_API_TOKEN: str = '56039c82a6c0a8f8573429ef4a172cafbf765bcc7530ff1e'
    EXOTEL_CALLER_ID: str = '08047187992'
    PETPOOJA_FETCH_MENU_URL: str = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/mapped_restaurant_menus"
    PETPOOJA_SAVE_ORDER_URL: str = "https://47pfzh5sf2.execute-api.ap-southeast-1.amazonaws.com/V1/save_order"
    PETPOOJA_UPDATE_ORDER_STATUS_URL: str = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/update_order_status"
    PETPOOJA_RIDER_STATUS_UPDATE_URL: str = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/rider_status_update"
    PETPOOJA_GET_STORE_STATUS_URL: str = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/get_store_status"
    PETPOOJA_UPDATE_STORE_STATUS_URL: str = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/update_store_status"
    PETPOOJA_APP_KEY: str = ""
    PETPOOJA_APP_SECRET: str = ""
    PETPOOJA_ACCESS_TOKEN: str = ""
    PETPOOJA_TIMEOUT_SECONDS: int = 30
    PETPOOJA_VERIFY_CALLBACK_CREDENTIALS: bool = False

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
