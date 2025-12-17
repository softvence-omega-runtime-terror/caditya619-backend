from fastapi import APIRouter, HTTPException, Form, UploadFile, Depends, File
from applications.user.models import User
from typing import Optional
from applications.user.vendor import VendorProfile, RestaurantProfile
from app.token import  create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required, vendor_required
from datetime import time
from app.utils.get_location import get_location_name
router = APIRouter(prefix='/vendor', tags=['Vendor Signup'])


@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(..., description="Enter a valid phone number +91XXXXXXXXXX"),
    name: Optional[str] = Form('Unknown User'),
    otp: str = Form(...),
):
    phone = await phone_number(phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid phone number.")

    if not await verify_otp(phone, otp, purpose="vendor_signup"):
        raise HTTPException(status_code=400, detail="OTP not verified.")

    async with in_transaction() as connection:
        user = await User.get_or_none(phone=phone)
        
        if user and user.is_vendor:
                raise HTTPException(status_code=400, detail="Already registered as vendor.")

        if not user:
            user = await User.create(phone=phone, name=name, is_vendor=True, using_db=connection)

    token_data = {
        "sub": str(user.id),
        "is_active": user.is_active,
        "is_rider": user.is_rider,
        "is_vendor": user.is_vendor,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    roles = [
        role
        for role, active in {
            "superuser": user.is_superuser,
            "staff": user.is_staff,
            "vendor": user.is_vendor,
            "rider": user.is_rider,
        }.items()
        if active
    ]

    return {
        "message": "User created successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "roles": roles,
        "token_type": "bearer",
    }
    
    
@router.put("/update-kyc/", response_model=dict)
async def update_kyc(
    nid: str = Form(...),
    vendor_type: str = Form(..., description='food/grocery/medicine'),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    file: UploadFile | None = File(None),
    current_user: User = Depends(vendor_required),
):
    # Ensure user is a vendor
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="You are not a vendor.")

    valid_types = ["food", "grocery", "medicine"]
    if vendor_type not in valid_types:
        raise HTTPException(status_code=400, detail="Invalid vendor type.")

    # Create or fetch vendor profile
    vendor_profile, created = await VendorProfile.get_or_create(user=current_user, defaults={"type": vendor_type})

    async with in_transaction() as conn:
        vendor_profile.nid = nid
        vendor_profile.type = vendor_type

        # File handling (depends on type)
        if file:
            if vendor_type == "food" or vendor_type == "medicine":
                vendor_profile.kyc_document = (
                    await update_file(file, vendor_profile.kyc_document, "kyc_document")
                    if vendor_profile.kyc_document
                    else await save_file(file, "kyc_document")
                )

        if latitude is not None:
            vendor_profile.latitude = latitude

        if longitude is not None:
            vendor_profile.longitude = longitude

        vendor_profile.kyc_status = "submitted"
        await vendor_profile.save(using_db=conn)

    return {
        "message": "KYC updated successfully",
        "vendor_profile": {
            "type": vendor_profile.type,
            "nid": vendor_profile.nid,
            "photo": vendor_profile.photo,
            "kyc_document": vendor_profile.kyc_document,
            "latitude": vendor_profile.latitude,
            "longitude": vendor_profile.longitude,
            "kyc_status": vendor_profile.kyc_status,
            "is_completed": vendor_profile.is_completed
        }
    }

@router.put("/toggle-active-status/", response_model=dict)
async def active_status(
    current_user: User = Depends(vendor_required),
):
    async with in_transaction() as conn:
        vendor_profile = await VendorProfile.get_or_none(user=current_user, using_db=conn)
        if not vendor_profile:
            raise HTTPException(status_code=404, detail="Vendor profile not found.")

        vendor_profile.is_active = not vendor_profile.is_active
        await vendor_profile.save(using_db=conn)

    return {
        "message": f"Vendor status updated successfully.",
        "status": vendor_profile.is_active,
    }



@router.get("/vendor-details/", response_model=dict)
async def vendor_details(
    current_user: User = Depends(vendor_required),
):
    vendor_profile = await VendorProfile.get_or_none(user=current_user)
    if not vendor_profile:
        raise HTTPException(status_code=200, detail="Vendor profile not found.")

    location_name = None
    if vendor_profile.latitude and vendor_profile.longitude:
        location_name = get_location_name(
            vendor_profile.latitude,
            vendor_profile.longitude
        )

    return {
        "message": "Vendor profile fetched successfully",
        "vendor_profile": {
            "id": current_user.id,
            "shop_name": current_user.name,
            "phone": current_user.phone,
            "photo": vendor_profile.photo,
            "owner_name": vendor_profile.owner_name,
            "type": vendor_profile.type,
            "is_active": vendor_profile.is_active,
            "open_time": str(vendor_profile.open_time)[:-3] if vendor_profile.open_time else None,
            "close_time": str(vendor_profile.close_time)[:-3] if vendor_profile.close_time else None,
            "is_completed": vendor_profile.is_completed,

            "latitude": vendor_profile.latitude,
            "longitude": vendor_profile.longitude,
            "location_name": location_name,
            "nid": vendor_profile.nid,
            "kyc_document": vendor_profile.kyc_document,
            "kyc_status": vendor_profile.kyc_status,
        }
    }


@router.put("/update-vendor-profile/", response_model=dict)
async def update_vendor_profile(
    owner_name: str = Form(...),
    photo: UploadFile | None = File(None),
    open_time: time = Form("09:00"),
    close_time: time = Form("22:00"),
    current_user: User = Depends(vendor_required),
):
    vendor_profile = await VendorProfile.get_or_none(user=current_user)
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    async with in_transaction() as conn:
        vendor_profile.owner_name = owner_name
        vendor_profile.open_time = open_time
        vendor_profile.close_time = close_time

        if photo:
            vendor_profile.photo = (
                await update_file(photo, vendor_profile.photo, "vendor_photos")
                if vendor_profile.photo else await save_file(photo, "vendor_photos")
            )
        await vendor_profile.save(using_db=conn)

    return {
        "message": "Vendor profile updated successfully",
        "vendor_profile": {
            "owner_name": vendor_profile.owner_name,
            "shop_name": current_user.name,
            "email": current_user.email,
            "photo": vendor_profile.photo,
            "open_time": str(vendor_profile.open_time) if vendor_profile.open_time else None,
            "close_time": str(vendor_profile.close_time) if vendor_profile.close_time else None,
            "is_completed": vendor_profile.is_completed,
            "kyc_status": vendor_profile.kyc_status,
        }
    }



