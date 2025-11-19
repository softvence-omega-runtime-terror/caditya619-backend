from fastapi import APIRouter, HTTPException, Form, UploadFile, Depends, File
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.token import  create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number
from app.utils.file_manager import save_file, update_file, delete_file
from app.token import get_current_user
from app.auth import permission_required

router = APIRouter(prefix='/vendor', tags=['Vendor Signup'])


@router.post("/signup/", response_model=dict)
async def signup(
    phone: str = Form(..., description="Enter a valid phone number +91XXXXXXXXXX"),
    name: str = Form(...),
    otp: str = Form(...),
    nid: str = Form(...),
    type: str = Form(..., description='food/groceries/medicine')
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
            await VendorProfile.get_or_create(
                user=user,
                defaults={
                    "type": type,
                    "nid": nid
                },
                using_db=connection,
            )

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
    fassai_file: UploadFile | None = File(None),
    drug_license_file: UploadFile | None = File(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    current_user: User = Depends(get_current_user)
):
    # Ensure user is a vendor
    if not current_user.is_vendor:
        raise HTTPException(status_code=403, detail="You are not a vendor.")

    # Fetch the actual VendorProfile
    vendor_profile = await VendorProfile.get_or_none(user=current_user)
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    # Validate required files based on vendor type
    if vendor_profile.type == "food" and not fassai_file:
        raise HTTPException(status_code=403, detail="FASSAI document is required for Food vendors.")
    if vendor_profile.type == "medicine" and not drug_license_file:
        raise HTTPException(status_code=403, detail="Drug License document is required for Medicine vendors.")

    async with in_transaction() as conn:
        # Update fields
        vendor_profile.nid = nid

        if fassai_file:
            if vendor_profile.fassai:
                vendor_profile.fassai = await update_file(fassai_file, vendor_profile.fassai, 'vendors_fassai')
            else:
                vendor_profile.fassai = await save_file(fassai_file, 'vendors_fassai')

        if drug_license_file:
            if vendor_profile.drug_license:
                vendor_profile.drug_license = await update_file(drug_license_file, vendor_profile.drug_license, 'vendors_drug_license')
            else:
                vendor_profile.drug_license = await save_file(drug_license_file, 'vendors_drug_license')

        if latitude is not None:
            vendor_profile.latitude = latitude
        if longitude is not None:
            vendor_profile.longitude = longitude

        # Reset status to submitted whenever KYC is updated
        vendor_profile.status = "submitted"

        await vendor_profile.save(using_db=conn)

    return {
        "message": "KYC updated successfully",
        "vendor_profile": {
            "nid": vendor_profile.nid,
            "fassai": vendor_profile.fassai,
            "drug_license": vendor_profile.drug_license,
            "latitude": vendor_profile.latitude,
            "longitude": vendor_profile.longitude,
            "status": vendor_profile.status,
        }
    }

@router.put("/update-vendor-status/", response_model=dict, dependencies=[Depends(permission_required("update_vendorprofile"))])
async def update_vendor_status(
    vendor_id: int = Form(...),
    new_status: str = Form(..., regex="^(submitted|verified|rejected)$"),
):
    async with in_transaction() as conn:
        vendor_profile = await VendorProfile.get_or_none(id=vendor_id, using_db=conn)
        if not vendor_profile:
            raise HTTPException(status_code=404, detail="Vendor profile not found.")

        vendor_profile.status = new_status
        await vendor_profile.save(using_db=conn)

    return {
        "message": f"Vendor profile status updated to '{new_status}' successfully.",
        "vendor_profile": {
            "id": vendor_profile.id,
            "user_id": vendor_profile.user_id,
            "status": vendor_profile.status,
            "type": vendor_profile.type,
            "nid": vendor_profile.nid,
        }
    }