from fastapi import APIRouter, HTTPException, Form, Depends, Query
from applications.user.vendor import VendorProfile, RestaurantProfile
from tortoise.transactions import in_transaction
from app.auth import permission_required

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

        if vendor_profile.type.lower() == "food" and new_status == "verified":
            restaurant_profile = await RestaurantProfile.get_or_none(vendor_id=vendor_profile.id)
            if not restaurant_profile:
                await RestaurantProfile.create(vendor=vendor_profile)

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


@router.get("/vendor-details/", response_model=dict, dependencies=[Depends(permission_required('view_vendorprofile'))])
async def vendor_details(
        vendor_id: int = Query(...)
):
    vendor_profile = await VendorProfile.get_or_none(user_id=vendor_id).select_related("user")

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
            "photo": vendor_profile.photo,  # photo stored in user
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