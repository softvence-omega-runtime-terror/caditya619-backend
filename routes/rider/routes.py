from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Header, Form, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, time
from tortoise import fields, models
from applications.user.models import User
from enum import Enum
from app.token import get_current_user
from applications.user.rider import RiderProfile, Vehicle, Zone, RiderAvailabilityStatus, HelpAndSupport, WorkDay, RiderCurrentLocation
from app.utils.file_manager import save_file, update_file, delete_file
from tortoise.exceptions import IntegrityError
from fastapi import Body
from tortoise.contrib.pydantic import pydantic_model_creator
from datetime import datetime, date, timezone
from pytz import utc
import logging
from .helper_functions import to_time
from app.utils.translator import translate





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


class IDType(str, Enum):
    aadhaar = "Aadhaar"
    pan = "PAN"
    voter_id = "Voter ID"



class RiderListResponse(BaseModel):
    count: int
    offset: int
    limit: int
    results: List[RiderProfile_Pydantic]





###############################################
#          Profile endpoints
##############################################


#profile related endpoints

@router.get("/rider-profile/me/")
async def rider_profile_me(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.filter(user=user).first()
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    return translate({"name": user.name, "email": user.email, "phone": user.phone,
            "driving_license": rider_profile.driving_license, "nid": rider_profile.nid,
            "profile_image": rider_profile.profile_image,}, lang)



@router.put("/rider-documents/me/", response_model=RiderProfile_Pydantic)
async def update_rider_documents_me(
     request: Request,
     id_type: IDType = Form(...),
     nid_num: str = Form(...),
     dl_num: str = Form(...),
     vi_reg_num: str = Form(...),
     pi: UploadFile = File(...),
     nid: UploadFile = File(...), 
     dl: UploadFile = File(...), 
     vr: UploadFile = File(...), 
     vi: UploadFile = File(...), 
     user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))

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


    if pi_path and nid_path and dl_path and vr_path and vi_path and nid_num and dl_num and vi_reg_num and id_type:
        rider_profile.profile_image = pi_path
        rider_profile.national_id_document = nid_path
        rider_profile.driving_license_document = dl_path
        rider_profile.vehicle_registration_document = vr_path
        rider_profile.vehicle_insurance_document = vi_path
        rider_profile.nid = nid_num
        rider_profile.driving_license = dl_num
        rider_profile.vehicle_registration_number = vi_reg_num
        rider_profile.nid_type = id_type.value

        rider_profile.is_document_uploaded = True
        rider_profile.verification_status = "Pending Approval"

    else:
        raise HTTPException(status_code=400, detail=translate("All documents must be provided", lang))
    
    
    await rider_profile.save()

    result = await RiderProfile_Pydantic.from_tortoise_orm(rider_profile)
    return translate(result, lang)


@router.get("/is-document-uploaded/")
async def is_document_update(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    return translate({"is_document_uploaded": rider_profile.is_document_uploaded}, lang)


@router.put("/rider/is-document-uploaded/")
async def update_is_document_uploaded(
    request: Request,
    is_document_uploaded: bool,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    rider_profile.is_document_uploaded = is_document_uploaded
    await rider_profile.save()

    return translate({"is_document_uploaded": is_document_uploaded}, lang)


@router.get("/is-verified")
async def verified_status(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    return translate({"verification_status": rider_profile.verification_status}, lang)




@router.get(
    "/rider-list",
    response_model=RiderListResponse,
    summary="Admin: List all riders (paginated)"
)
async def list_riders(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    lng = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not current_user.is_superuser:
        raise HTTPException(403, translate("Superuser access required", lng))

    # Use .count() and keep queryset, don't convert to list early!
    total = await RiderProfile.all().count()
    
    # Keep it as queryset → works with from_queryset()
    riders_qs = RiderProfile.all().order_by("-created_at").offset(offset).limit(limit)
    riders_data = await RiderProfile_Pydantic.from_queryset(riders_qs)

    return RiderListResponse(
        count=translate(total, lng),
        offset=translate(offset, lng),
        limit=translate(limit, lng),
        results=translate(riders_data, lng)
    )







@router.put("/rider-profile/me/")
async def update_rider_profile_me(
    request: Request,
    profile_data: RiderProfileUpdateModel,
    user: User = Depends(get_current_user)
):
    lng = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lng))
    
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
    return translate({"name": user.name, "email": user.email, "phone": user.phone,
            "driving_license": rider_profile.driving_license, "nid": rider_profile.nid,
            "profile_image": rider_profile.profile_image,}, lng)



@router.delete("/rider-profile/me/")
async def delete_rider_profile_me(
    request: Request,
    rider_profile_id: Optional[int] =  Query(None),
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if user.is_superuser:
        rider_profile = await RiderProfile.get_or_none(id=rider_profile_id)
        rider = await User.get_or_none(id=rider_profile.user_id)
        if not rider_profile:
            raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    elif user.is_rider:
        rider_profile = await RiderProfile.get_or_none(user=user)
        rider = user
        if not rider_profile:
            raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    else:
        raise HTTPException(status_code=403, detail=translate("Not authorized to delete this rider profile", lang))
    
    # Optionally, delete related data (vehicles, documents, etc.) here

    # rider.is_rider = False
    # await rider.save()

    await rider_profile.delete()
    await rider.delete()
    
    return {"message": translate("Rider profile deleted successfully", lang)}





@router.get("/profile/completion")
async def get_profile_completion(request: Request, current_user: User = Depends(get_current_user)):
    """
    Returns profile completion percentage and list of missing fields
    Only counts the 10 fields specified in requirements
    """
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get_or_none(user=current_user)
    if not rider:
        raise HTTPException(404, translate("Rider profile not found", lang))

    # List of fields that count toward completion
    completion_fields = {
        "Full Name": current_user.name,
        "Phone": current_user.phone,
        "Email": current_user.email,
        "Driving License": rider.driving_license,
        "National ID (NID)": rider.nid,
        "Profile Image": rider.profile_image,
        "National ID Document": rider.national_id_document,
        "Driving License Document": rider.driving_license_document,
        "Vehicle Registration Document": rider.vehicle_registration_document,
        "Vehicle Insurance Document": rider.vehicle_insurance_document,
    }

    total_fields = len(completion_fields)  # 10
    filled_count = 0
    missing_fields = []

    for field_name, value in completion_fields.items():
        # Consider field filled if it's not None, not empty string, and not just whitespace
        if value and str(value).strip():
            filled_count += 1
        else:
            missing_fields.append(field_name)

    percentage = int((filled_count / total_fields) * 100)

    return translate({
        "completion_percentage": percentage,
        "total_fields": total_fields,
        "filled_fields": filled_count,
        "missing_fields": missing_fields,
        "is_complete": percentage == 100,
        "message": f"Profile is {percentage}% complete"
    }, lang)



#*****************************************************
#            Vehicle related endpoints
#*****************************************************

@router.get("/list/vehicles/", response_model=List[VehicleOut])
async def list_vehicles_me(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    vehicles = await Vehicle.filter(rider_profile=rider_profile)
    print("Vehicles fetched:", vehicles)
    if not vehicles:
        raise HTTPException(status_code=404, detail=translate("No vehicles found", lang))
    return [await VehicleOut.from_tortoise_orm(translate(vehicle, lang)) for vehicle in vehicles]




@router.get("/vehicles/id/{vehicle_id}/", response_model=VehicleOut)
async def list_vehicles_me(request: Request, vehicle_id: int, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    vehicle = await Vehicle.filter(id=vehicle_id, rider_profile=rider_profile).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=translate("Vehicle not found", lang))
    vehicle_payload = await VehicleOut.from_tortoise_orm(vehicle)
    return translate(vehicle_payload, lang)

    



@router.post("/vehicles/me/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def add_vehicle_me(
    request: Request,
    vehicle_data: VehicleCreate,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))

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
        raise HTTPException(status_code=400, detail=translate("Vehicle with this license_plate_number already exists", lang))

    # return Pydantic representation (async helper for Tortoise -> Pydantic)
    return await VehicleOut.from_tortoise_orm(translate(new_vehicle, lang))

@router.put("/vehicles/{vehicle_id}/update/", response_model=VehicleOut, status_code=status.HTTP_200_OK)
async def update_vehicle_me(
    request: Request,
    vehicle_id: int,
    vehicle_data: VehicleCreate,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    try:
        vehicle = await Vehicle.get_or_none(id=vehicle_id, rider_profile=rider_profile)
        vehicle.vehicle_type = vehicle_data.vehicle_type
        vehicle.model = vehicle_data.model
        vehicle.license_plate_number = vehicle_data.license_plate_number
        
        await vehicle.save()
        return await VehicleOut.from_tortoise_orm(vehicle)
    except Vehicle.DoesNotExist:
        raise HTTPException(status_code=404, detail=translate("Vehicle not found", lang))


@router.delete("/vehicles/{vehicle_id}/delete/", response_model=dict)
async def remove_vehicle_me(
    request: Request,
    vehicle_id: int,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    try:
        vehicle = await Vehicle.get(id=vehicle_id, rider_profile=rider_profile)
        await vehicle.delete()
        return translate({"message": f"Vehicle with ID {vehicle_id} has been deleted."}, lang)
    except Vehicle.DoesNotExist:
        raise HTTPException(status_code=404, detail=translate("Vehicle not found", lang))
    



#*****************************************************
#           current location endpoints
#*****************************************************

@router.post("/rider-location/me/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def update_rider_location_me(
    request: Request,
    latitude: float = Form(...),
    longitude: float = Form(...),
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    
    current_location = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
    if not current_location:     
        new_location = await RiderCurrentLocation.create(
            rider_profile=rider_profile,
            latitude=latitude,
            longitude=longitude
        )
        await new_location.save()
        return translate({"message": "Location created successfully"}, lang)
    else:
        current_location.latitude = latitude
        current_location.longitude = longitude
        await current_location.save()
   
    return translate({"message": "Location updated successfully"}, lang)
    


@router.get("/rider-location/me/", response_model=dict)
async def get_rider_location_me(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    current_location = await RiderCurrentLocation.get_or_none(rider_profile=rider_profile)
    if not current_location:
        raise HTTPException(status_code=404, detail=translate("Current location not found", lang))
    return translate({"latitude": current_location.latitude, "longitude": current_location.longitude}, lang)




#*****************************************************
#            Availablity Status endpoints
#*****************************************************


@router.post("/rider-availability/me/", response_model=AvailabilityStatusOut, status_code=status.HTTP_201_CREATED)
async def set_availability_status(
    request: Request,
    is_available: bool = Form(None),
    start_at: Optional[time] = Form(None),
    end_at: Optional[time] = Form(None),
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))

    availability_status, created= await RiderAvailabilityStatus.get_or_create(rider_profile=rider_profile)
    availability_status.is_available = is_available
    availability_status.strat_at = start_at
    availability_status.end_at = end_at
    await availability_status.save()
    return await AvailabilityStatusOut.from_tortoise_orm(translate(availability_status, lang))




@router.get("/rider-availability/me/", response_model=AvailabilityStatusOut)
async def get_availability_status(request: Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))

    availability_status = await RiderAvailabilityStatus.get_or_none(rider_profile_id=rider_profile.id)
    if not availability_status:
        raise HTTPException(status_code=404, detail=translate("Availability status not set", lang))

    # Build response dict matching the Pydantic model field names
    data = {
        "id": availability_status.id,                         # required
        "is_available": availability_status.is_available,
        # use the actual ORM attribute name (you used 'strat_at' in the model)
        "strat_at": to_time(availability_status.strat_at),    # note: 'strat_at' not 'start_at'
        "end_at":   to_time(availability_status.end_at),
        "updated_at": availability_status.updated_at,         # required
        # include any other fields AvailabilityStatusOut expects (e.g., rider_profile_id)
    }

    return AvailabilityStatusOut(**data)
 






#*****************************************************
#            Help and Support endpoints 
#*****************************************************

@router.post("/help-and-support/me/", response_model=HelpAndSupportOut, status_code=status.HTTP_201_CREATED)
async def submit_help_and_support_request(
    request: Request,
    subject: str = Form(...),
    description: str = Form(...),
    attachments: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    
    if attachments:
        attachments_path = await save_file(
            attachments, upload_to="HelpAndSupport", allowed_extensions=['png', 'jpg', 'svg', 'jpeg', 'pdf']
        )
    else:
        attachments_path = None

    help_request = await HelpAndSupport.create(
        rider_id=rider_profile.id,
        subject=subject,
        description=description,
        attachment=attachments_path
    )
    return await HelpAndSupportOut.from_tortoise_orm(translate(help_request, lang))



@router.get("/help-and-support-requests/me/", response_model=List[HelpAndSupportOut])
async def list_help_and_support_requests_me(
    request: Request,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider_profile = await RiderProfile.get_or_none(user=user)
    if not rider_profile:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    requests = await HelpAndSupport.filter(rider_id=rider_profile.id)
    return [await HelpAndSupportOut.from_tortoise_orm(translate(request, lang)) for request in requests]





#*****************************************************
#            Go Online / Offline endpoints
#*****************************************************

LOCAL_TZ = datetime.now().astimezone().tzinfo

@router.put("/go-online-offline")
async def go_online_offline(
    request: Request,
    is_online: bool = Form(...),
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get(user=user)
    # today in system local date
    today = datetime.now(LOCAL_TZ).date()

    workday, _ = await WorkDay.get_or_create(
        rider=rider, date=today,
        defaults={"hours_worked": 0.0, "order_offer_count": 0}
    )

    if is_online:
        if rider.is_available:
            return translate({"message": "Already online"}, lang)

        now_local = datetime.now(LOCAL_TZ)                 # full aware datetime in local tz
        rider.is_available = True
        rider.online_start_time = now_local
        await rider.save(update_fields=["is_available", "online_start_time"])

        return translate({
            "message": "Rider is now online",
            "session_started_local": now_local.isoformat(),
            "local_time_readable": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "hint": "Wait a minute then go offline to test"
        }, lang)

    else:
        # GOING OFFLINE
        if not rider.is_available or not rider.online_start_time:
            # clear state and return early
            rider.is_available = False
            rider.online_start_time = None
            await rider.save(update_fields=["is_available", "online_start_time"])
            return translate({"message": "No active session"}, lang)

        # re-fetch to avoid stale instance
        fresh = await RiderProfile.get(id=rider.id)
        start = fresh.online_start_time

        # normalize start -> system local tz
        if start is None:
            rider.is_available = False
            rider.online_start_time = None
            await rider.save(update_fields=["is_available", "online_start_time"])
            return translate({"message": "No start time recorded; cleared state"}, lang)

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

        return translate({
            "message": "Rider is now offline",
            "this_session_hours": round(duration_hours, 4),
            "duration_minutes": round(duration_hours * 60, 2),
            "total_today_hours": round(workday.hours_worked, 4),
            "session_from_local": start.isoformat(),
            "session_to_local": end.isoformat(),
            "session_from_local_readable": start.strftime("%Y-%m-%d %I:%M %p"),
            "session_to_local_readable": end.strftime("%Y-%m-%d %I:%M %p"),
            "success": "Using system local time for all timestamps"
        }, lang)




@router.get("/is-online-status/")
async def is_online_status(
    request: Request,
    user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    rider = await RiderProfile.get(user=user)
    if not rider:
        raise HTTPException(status_code=404, detail=translate("Rider profile not found", lang))
    return translate({
        "is_online": rider.is_available,
        "online_start_time": rider.online_start_time.isoformat() if rider.online_start_time else None
    }, lang)


#*****************************************************
