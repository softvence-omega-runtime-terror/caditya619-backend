from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time
from tortoise import fields, models
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, Vehicle, Zone, RiderZoneAssignment, RiderAvailabilityStatus
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from fastapi import Body
from tortoise.contrib.pydantic import pydantic_model_creator


# from datetime import time as _time
# from app.utils.websocket_manager import manager
# import json
# from app.redis import redis_client
# from starlette.websockets import WebSocketDisconnect, WebSocket
# import asyncio
# from app.utils.map_distance_ETA import haversine, estimate_eta
# from fastapi.responses import HTMLResponse
# from app.redis import get_redis




from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/rider_state/" , tags=['Rider State'])



