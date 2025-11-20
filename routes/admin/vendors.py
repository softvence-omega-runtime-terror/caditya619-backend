from fastapi import APIRouter, HTTPException, Form, UploadFile, Depends, File
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.token import create_access_token, create_refresh_token
from app.utils.otp_manager import verify_otp
from tortoise.transactions import in_transaction
from app.utils.phone_number import phone_number
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required, vendor_required

router = APIRouter(prefix='/vendor', tags=['Vendor Detals & KYC'])

@router.put("/update-vendor-status/", response_model=dict, dependencies=[Depends(permission_required("update_vendorprofile"))])
async def update_vendor_status(
    vendor_id: int = Form(...),
    new_status: str = Form(..., regex="^(submitted|verified|rejected)$"),
):
    async with in_transaction() as conn:
        vendor_profile = await VendorProfile.get_or_none(user_id=vendor_id, using_db=conn)
        if not vendor_profile:
            raise HTTPException(status_code=404, detail="Vendor profile not found.")

        vendor_profile.kyc_status = new_status
        await vendor_profile.save(using_db=conn)

    return {
        "message": f"Vendor profile status updated to '{new_status}' successfully.",
        "vendor_profile": {
            "id": vendor_profile.id,
            "user_id": vendor_profile.user_id,
            "kyc_status": vendor_profile.kyc_status,
            "type": vendor_profile.type,
            "nid": vendor_profile.nid,
        }
    }


@router.get("/vendor-details/", response_model=dict, dependencies=[Depends(vendor_required)])
async def vendor_details(
        vendor_id: int = Form(...),
):
    vendor_profile = await VendorProfile.get_or_none(user_id=vendor_id)
    if not vendor_profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    return {
        "message": "Vendor profile fetched successfully",
        "vendor_profile": {
            "id": vendor_profile.user.id,
            "shop_name": vendor_profile.user.name,
            "email": vendor_profile.user.email,
            "phone": vendor_profile.user.phone,
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


@router.put("/update-vendor-profile/", response_model=dict, dependencies=[Depends(permission_required("view_vendorprofile"))])
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