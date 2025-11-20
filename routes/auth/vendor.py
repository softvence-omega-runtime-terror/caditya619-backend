from fastapi import APIRouter, HTTPException, Form, UploadFile, Depends, File
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.token import  create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required, vendor_required

router = APIRouter(prefix='/vendor', tags=['Vendor Signup'])


@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(..., description="Enter a valid phone number +91XXXXXXXXXX"),
    name: str = Form(...),
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
    file: UploadFile | None = File(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    vendor_type: str = Form(..., description='food/grocery/medicine'),
    current_user: User = Depends(vendor_required)
):
    # Ensure user is a vendor
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="You are not a vendor.")

    # Create or fetch vendor profile
    vendor_profile, created = await VendorProfile.get_or_create(user=current_user)

    async with in_transaction() as conn:
        vendor_profile.nid = nid
        vendor_profile.type = vendor_type

        if file:
            if vendor_type == "food":
                vendor_profile.fassai = (
                    await update_file(file, vendor_profile.fassai, "vendors_fassai")
                    if vendor_profile.fassai
                    else await save_file(file, "vendors_fassai")
                )

            elif vendor_type == "medicine":
                vendor_profile.drug_license = (
                    await update_file(file, vendor_profile.drug_license, "vendors_drug_license")
                    if vendor_profile.drug_license
                    else await save_file(file, "vendors_drug_license")
                )

        # Update location fields if provided
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
            "fassai": vendor_profile.fassai,
            "drug_license": vendor_profile.drug_license,
            "latitude": vendor_profile.latitude,
            "longitude": vendor_profile.longitude,
            "kyc_status": vendor_profile.kyc_status
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
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    return {
        "message": "Vendor profile fetched successfully",
        "vendor_profile": {
            "id": current_user.id,
            "shop_name": current_user.name,
            "email": current_user.email,
            "phone": current_user.phone,
            "owner_name": vendor_profile.owner_name,
            "type": vendor_profile.type,
            "photo": vendor_profile.photo,
            "is_active": vendor_profile.is_active,
            "open_time": str(vendor_profile.open_time) if vendor_profile.open_time else None,
            "close_time": str(vendor_profile.close_time) if vendor_profile.close_time else None,
            "is_completed": vendor_profile.is_completed,

            "latitude": vendor_profile.latitude,
            "longitude": vendor_profile.longitude,
            "nid": vendor_profile.nid,
            "fassai": vendor_profile.fassai,
            "drug_license": vendor_profile.drug_license,
            "kyc_status": vendor_profile.kyc_status,
        }
    }


@router.put("/update-vendor-profile/", response_model=dict)
async def update_vendor_profile(
    owner_name: str = Form(...),
    email: str = Form(None),
    photo: UploadFile | None = File(None),
    open_time: str = Form(None),
    close_time: str = Form(None),
    current_user: User = Depends(vendor_required),
):
    vendor_profile = await VendorProfile.get_or_none(user=current_user)
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    async with in_transaction() as conn:
        current_user.email = email
        await current_user.save(using_db=conn)

        vendor_profile.owner_name = owner_name
        vendor_profile.open_time = open_time
        vendor_profile.close_time = close_time

        if photo:
            vendor_profile.photo = (
                await update_file(photo, vendor_profile.photo, "vendor_photos")
                if vendor_profile.photo
                else await save_file(photo, "vendor_photos")
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
        }
    }