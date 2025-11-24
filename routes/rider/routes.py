from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time
from tortoise import fields, models
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, Vehicle, Zone, RiderZoneAssignment, RiderAvailabilityStatus, HelpAndSupport, WorkDay
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from fastapi import Body
from tortoise.contrib.pydantic import pydantic_model_creator
from datetime import datetime, date, timezone
from pytz import utc
import logging


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

router = APIRouter(tags=['Rider'])


logger = logging.getLogger(__name__)

###############################################
#           pydantic models
##############################################

RiderProfile_Pydantic = pydantic_model_creator(RiderProfile, name="RiderProfile", exclude=[])
RiderProfileIn_Pydantic = pydantic_model_creator(RiderProfile, name="RiderProfileIn", exclude_readonly=True)
VehicleOut = pydantic_model_creator(Vehicle, name="VehicleOut")
ZoneOut = pydantic_model_creator(Zone, name="ZoneOut")
AvailabilityStatusOut = pydantic_model_creator(RiderAvailabilityStatus, name="AvailabilityStatusOut")
HelpAndSupportOut = pydantic_model_creator(HelpAndSupport, name="HelpAndSupportOut")


class RiderProfileUpdateModel(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    driving_license: Optional[str] = None
    nid: Optional[str] = None

    class Config:
        orm_mode = True

class VehicleType(str, Enum):
    car = "car"
    bike = "bike"
    truck = "truck"
    van = "van"

class VehicleCreate(BaseModel):
    vehicle_type: VehicleType
    model: str
    license_plate_number: str





###############################################
#           endpoints
##############################################


#profile related endpoints

@router.get("/rider-profile/me/")
async def rider_profile_me(user: User = Depends(get_current_user)):
    rider_profile = await RiderProfile.filter(user=user).first()
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    return {"name": user.name, "email": user.email, "phone": user.phone,
            "driving_license": rider_profile.driving_license, "nid": rider_profile.nid,
            "profile_image": rider_profile.profile_image,}



@router.put("/rider-documents/me/", response_model=RiderProfile_Pydantic)
async def update_rider_documents_me(
     pi: UploadFile = File(...),
     nid: UploadFile = File(...), 
     dl: UploadFile = File(...), 
     vr: UploadFile = File(...), 
     vi: UploadFile = File(...), 
     user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    # Here you would normally handle file saving and get the file paths
    if pi and pi.filename:
         pi_path = await update_file(
            pi, rider_profile.profile_image, upload_to="Documents", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
    if nid and nid.filename:
         nid_path = await update_file(
            nid, rider_profile.national_id_document, upload_to="Documents", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
    if dl and dl.filename:
         dl_path = await update_file(
            dl, rider_profile.driving_license_document, upload_to="Documents", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
    if vr and vr.filename:
         vr_path = await update_file(
            vr, rider_profile.vehicle_registration_document, upload_to="Documents", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
    if vi and vi.filename:
         vi_path = await update_file(
            vi, rider_profile.vehicle_insurance_document, upload_to="Documents", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
         
    
    if pi_path and nid_path and dl_path and vr_path and vi_path:
        rider_profile.profile_image = pi_path
        rider_profile.national_id_document = nid_path
        rider_profile.driving_license_document = dl_path
        rider_profile.vehicle_registration_document = vr_path
        rider_profile.vehicle_insurance_document = vi_path

    else:
        raise HTTPException(status_code=400, detail="All documents must be provided")
    
    await rider_profile.save()
    return await RiderProfile_Pydantic.from_tortoise_orm(rider_profile)








@router.put("/rider-profile/me/")
async def update_rider_profile_me(
    profile_data: RiderProfileUpdateModel,
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    if profile_data.driving_license is not None:
        rider_profile.driving_license = profile_data.driving_license
    if profile_data.nid is not None:
        rider_profile.nid = profile_data.nid    
    if profile_data.name is not None:
        user.name = profile_data.name
    if profile_data.email is not None:
        user.email = profile_data.email

    
    
    await rider_profile.save()
    await user.save()
    return {"name": user.name, "email": user.email, "phone": user.phone,
            "driving_license": rider_profile.driving_license, "nid": rider_profile.nid,
            "profile_image": rider_profile.profile_image,}



#*****************************************************
#            Vehicle related endpoints
#*****************************************************


@router.get("/vehicles/{vehicle_id}/", response_model=VehicleOut)
async def list_vehicles_me(vehicle_id: int, user: User = Depends(get_current_user)):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    vehicle = await Vehicle.filter(id=vehicle_id, rider_profile=rider_profile).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    vehicle_payload = await VehicleOut.from_tortoise_orm(vehicle)
    return vehicle_payload
    



@router.post("/vehicles/me/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def add_vehicle_me(
    vehicle_data: VehicleCreate,
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    try:
        # create using Tortoise .create() (async)
        new_vehicle = await Vehicle.create(
            rider_profile_id=rider_profile.id,
            vehicle_type=vehicle_data.vehicle_type.value,
            model=vehicle_data.model,
            license_plate_number=vehicle_data.license_plate_number
        )
    except IntegrityError as exc:
        # license plate unique constraint likely violated
        raise HTTPException(status_code=400, detail="Vehicle with this license_plate_number already exists")

    # return Pydantic representation (async helper for Tortoise -> Pydantic)
    return await VehicleOut.from_tortoise_orm(new_vehicle)

@router.put("/vehicles/{vehicle_id}/update/", response_model=VehicleOut, status_code=status.HTTP_200_OK)
async def update_vehicle_me(
    vehicle_id: int,
    vehicle_data: VehicleCreate,
    user: User = Depends(get_current_user)
):
    print("Received data:")
    rider_profile = await RiderProfile.get_or_none(user=user)
    print("Rider profile:", rider_profile)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    try:
        vehicle = await Vehicle.get_or_none(id=vehicle_id, rider_profile=rider_profile)
        vehicle.vehicle_type = vehicle_data.vehicle_type
        vehicle.model = vehicle_data.model
        vehicle.license_plate_number = vehicle_data.license_plate_number
        print("Updating vehicle:", vehicle)
        await vehicle.save()
        return await VehicleOut.from_tortoise_orm(vehicle)
    except Vehicle.DoesNotExist:
        raise HTTPException(status_code=404, detail="Vehicle not found")


@router.delete("/vehicles/{vehicle_id}/delete/", response_model=dict)
async def remove_vehicle_me(
    vehicle_id: int,
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    try:
        vehicle = await Vehicle.get(id=vehicle_id, rider_profile=rider_profile)
        await vehicle.delete()
        return {"message": f"Vehicle with ID {vehicle_id} has been deleted."}
    except Vehicle.DoesNotExist:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    




#*****************************************************
#            Zone endpoints
#*****************************************************



@router.get("/zones/{zone_id}/me/")
async def list_assigned_zones_me(zone_id:int, user: User = Depends(get_current_user)):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    zones = await Zone.filter(id=zone_id).first()
    if not zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    zone_assignments = await RiderZoneAssignment.create(rider_profile=rider_profile, zone=zones)

    await zone_assignments.save()
    
    return zone_assignments


@router.post("/create-zone/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_zone(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    user: User = Depends(get_current_user)
):
    # In a real application, you would check if the user has admin privileges here
    existing_zone = await Zone.get_or_none(name=name)
    if existing_zone:
        raise HTTPException(status_code=400, detail="Zone with this name already exists")
    new_zone = await Zone.create(name=name, description=description)
    return {"message": f"Zone '{new_zone.name}' created successfully.", "zone_id": new_zone.id}



@router.get("/zones-list/")
async def list_all_zones(user: User = Depends(get_current_user)):
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to view all zones")
    zones = await Zone.all()
    return zones


@router.put("/zones/{zone_id}/update/", response_model=ZoneOut, status_code=status.HTTP_200_OK)
async def update_zone(
    zone_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user: User = Depends(get_current_user)
):
    # In a real application, you would check if the user has admin privileges here
    zone = await Zone.get_or_none(id=zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    if name is not None:
        zone.name = name
    if description is not None:
        zone.description = description
    await zone.save()
    return await ZoneOut.from_tortoise_orm(zone)


@router.delete("/zones/{zone_id}/delete/", response_model=dict)
async def delete_zone(
    zone_id: int,
    user: User = Depends(get_current_user)
):
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to delete zones")
    # In a real application, you would check if the user has admin privileges here
    zone = await Zone.get_or_none(id=zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    await zone.delete()
    return {"message": f"Zone with ID {zone_id} has been deleted."}




#*****************************************************
#            Availablity Status endpoints
#*****************************************************


@router.post("/rider-availability/me/", response_model=AvailabilityStatusOut, status_code=status.HTTP_201_CREATED)
async def set_availability_status(
    is_available: bool = Form(None),
    start_at: Optional[time] = Form(None),
    end_at: Optional[time] = Form(None),
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    availability_status, created= await RiderAvailabilityStatus.get_or_create(rider_profile=rider_profile)
    availability_status.is_available = is_available
    availability_status.strat_at = start_at
    availability_status.end_at = end_at
    await availability_status.save()
    return await AvailabilityStatusOut.from_tortoise_orm(availability_status)



@router.get("/rider-availability/me/", response_model=List[AvailabilityStatusOut])
async def get_availability_status(
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    availability_status = await RiderAvailabilityStatus.get_or_none(rider_profile=rider_profile)
    if not availability_status:
        raise HTTPException(status_code=404, detail="Availability status not set")
    #return await AvailabilityStatusOut.from_tortoise_orm(availability_status)
    return [await AvailabilityStatusOut.from_tortoise_orm(availability_status) for availability_status in [availability_status]]
    







#*****************************************************
#            Help and Support endpoints 
#*****************************************************

@router.post("/help-and-support/me/", response_model=HelpAndSupportOut, status_code=status.HTTP_201_CREATED)
async def submit_help_and_support_request(
    subject: str = Form(...),
    description: str = Form(...),
    attachments: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    if attachments:
        attachments_path = await save_file(
            attachments, upload_to="HelpAndSupport", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
        print("Attachments saved at:", attachments_path)
    else:
        attachments_path = None

    help_request = await HelpAndSupport.create(
        rider_id=rider_profile.id,
        subject=subject,
        description=description,
        attachment=attachments_path
    )
    return await HelpAndSupportOut.from_tortoise_orm(help_request)



@router.get("/help-and-support-requests/me/", response_model=List[HelpAndSupportOut])
async def list_help_and_support_requests_me(
    user: User = Depends(get_current_user)
):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    requests = await HelpAndSupport.filter(rider_id=rider_profile.id)
    return [await HelpAndSupportOut.from_tortoise_orm(request) for request in requests]





# Add this field to RiderProfile model (one-time)
#online_start_time = fields.DatetimeField(null=True, default=None)

LOCAL_TZ = datetime.now().astimezone().tzinfo

@router.put("/go-online-offline")
async def go_online_offline(
    is_online: bool = Form(...),
    user: User = Depends(get_current_user)
):
    rider = await RiderProfile.get(user=user)
    # today in system local date
    today = datetime.now(LOCAL_TZ).date()

    workday, _ = await WorkDay.get_or_create(
        rider=rider, date=today,
        defaults={"hours_worked": 0.0, "order_offer_count": 0}
    )

    if is_online:
        if rider.is_available:
            return {"message": "Already online"}

        now_local = datetime.now(LOCAL_TZ)                 # full aware datetime in local tz
        rider.is_available = True
        rider.online_start_time = now_local
        await rider.save(update_fields=["is_available", "online_start_time"])

        return {
            "message": "Rider is now online",
            "session_started_local": now_local.isoformat(),
            "local_time_readable": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "hint": "Wait a minute then go offline to test"
        }

    else:
        # GOING OFFLINE
        if not rider.is_available or not rider.online_start_time:
            # clear state and return early
            rider.is_available = False
            rider.online_start_time = None
            await rider.save(update_fields=["is_available", "online_start_time"])
            return {"message": "No active session"}

        # re-fetch to avoid stale instance
        fresh = await RiderProfile.get(id=rider.id)
        start = fresh.online_start_time

        # normalize start -> system local tz
        if start is None:
            rider.is_available = False
            rider.online_start_time = None
            await rider.save(update_fields=["is_available", "online_start_time"])
            return {"message": "No start time recorded; cleared state"}

        if start.tzinfo is None:
            # treat naive DB times as already system-local -> mark them as local
            start = start.replace(tzinfo=LOCAL_TZ)
        else:
            # convert any other timezone to system local
            start = start.astimezone(LOCAL_TZ)

        end = datetime.now(LOCAL_TZ)

        duration_seconds = (end - start).total_seconds()
        # Defensive clamping
        if duration_seconds < 0:
            duration_seconds = 0.0
        if duration_seconds > 24 * 3600:
            # suspiciously large session -> clamp or flag (here we clamp)
            duration_seconds = 0.0

        duration_hours = duration_seconds / 3600.0

        # update workday
        workday.hours_worked = (workday.hours_worked or 0.0) + duration_hours
        await workday.save()

        # reset rider
        rider.is_available = False
        rider.online_start_time = None
        await rider.save(update_fields=["is_available", "online_start_time"])

        return {
            "message": "Rider is now offline",
            "this_session_hours": round(duration_hours, 4),
            "duration_minutes": round(duration_hours * 60, 2),
            "total_today_hours": round(workday.hours_worked, 4),
            "session_from_local": start.isoformat(),
            "session_to_local": end.isoformat(),
            "session_from_local_readable": start.strftime("%Y-%m-%d %I:%M %p"),
            "session_to_local_readable": end.strftime("%Y-%m-%d %I:%M %p"),
            "success": "Using system local time for all timestamps"
        }



#*****************************************************
