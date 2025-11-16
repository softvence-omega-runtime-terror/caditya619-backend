from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time
from tortoise import fields, models
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, Vehicle, Zone, RiderZoneAssignment, RiderAvailabilityStatus, RiderCurrentLocation
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

router = APIRouter(tags=['Rider'])

###############################################
#           pydantic models
##############################################

RiderProfile_Pydantic = pydantic_model_creator(RiderProfile, name="RiderProfile", exclude=[])
RiderProfileIn_Pydantic = pydantic_model_creator(RiderProfile, name="RiderProfileIn", exclude_readonly=True)
VehicleOut = pydantic_model_creator(Vehicle, name="VehicleOut")
ZoneOut = pydantic_model_creator(Zone, name="ZoneOut")
AvailabilityStatusOut = pydantic_model_creator(RiderAvailabilityStatus, name="AvailabilityStatusOut")


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




@router.put("/admin-verify-rider/{rider_id}/", response_model=RiderProfile_Pydantic)
async def admin_verify_rider(
    rider_id: int = Path(..., description="The ID of the rider to verify"),
    is_verified: bool = Body(..., embed=True, description="Verification status to set"),
    user: User = Depends(get_current_user)
):
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to verify riders")
    
    rider_profile = await RiderProfile.get_or_none(id=rider_id)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    rider_profile.is_verified = is_verified
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



@router.put("/rider-online-offline/")
async def go_online_offline(is_available: bool, user: User=Depends(get_current_user)):
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    rider_profile.is_available = is_available

    await rider_profile.save()
    await user.save()

    return {"is_available":rider_profile.is_available}



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




@router.post("/rider-current-location")
async def rider_current_location(lat:float, lng:float, user:User = Depends(get_current_user)):
    if not user.is_rider:
        raise HTTPException(status_code=204, detail="Must be rider to set the location")
    
    rider_profile = await RiderProfile.get_or_none(user=user)

    
    current_location = await RiderCurrentLocation.create(
        rider_profile = rider_profile,
        latitude = lat, 
        longitude = lng
    )

    await current_location.save()

    return {"rider":rider_profile.id, "lat":current_location.latitude, "long":current_location.longitude}




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







