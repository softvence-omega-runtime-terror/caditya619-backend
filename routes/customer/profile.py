# routes/customer/profile.py
from fastapi import APIRouter, HTTPException, Depends, status
from applications.user.models import User
from applications.customer.models import *
from applications.customer.schemas import CustomerProfileSchema, CustomerProfileResponseSchema
from app.token import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/", response_model=CustomerProfileResponseSchema)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get customer profile"""
    # ✅ Fixed: Filter by user, not by id
    profile = await CustomerProfile.filter(user=current_user).prefetch_related("user").first()
    
    if not profile:
        # Create profile if it doesn't exist
        profile = await CustomerProfile.create_for_user(current_user)
        await profile.fetch_related("user")
    
    return {
        "success": True,
        "message": "Profile retrieved successfully",
        "data": {
            "id": profile.id,
            "user_id": profile.user.id,
            "name": profile.user.name,
            "email": profile.user.email,
            "phone": profile.user.phone,
            "photo": profile.user.photo,
            "address_1": profile.add1,
            "address_2": profile.add2,
            "postal_code": profile.postal_code
        }
    }


@router.post("/", response_model=CustomerProfileResponseSchema)
async def create_or_update_profile(
    profile_data: CustomerProfileSchema,
    current_user: User = Depends(get_current_user)
):
    """Create or update customer profile"""
    # Check if profile exists
    profile = await CustomerProfile.filter(user=current_user).first()
    
    if profile:
        # Update existing profile
        profile.add1 = profile_data.address_1
        profile.add2 = profile_data.address_2
        profile.postal_code = profile_data.postal_code
        await profile.save()
        message = "Profile updated successfully"
    else:
        # Create new profile
        profile = await CustomerProfile.create(
            user=current_user,
            add1=profile_data.address_1,
            add2=profile_data.address_2,
            postal_code=profile_data.postal_code
        )
        message = "Profile created successfully"
    
    # Update user info if provided
    if profile_data.name:
        current_user.name = profile_data.name
    if profile_data.email:
        current_user.email = profile_data.email
    if profile_data.photo:
        current_user.photo = profile_data.photo
    
    await current_user.save()
    await profile.fetch_related("user")
    
    return {
        "success": True,
        "message": message,
        "data": {
            "id": profile.id,
            "user_id": profile.user.id,
            "name": profile.user.name,
            "email": profile.user.email,
            "phone": profile.user.phone,
            "photo": profile.user.photo,
            "address_1": profile.add1,
            "address_2": profile.add2,
            "postal_code": profile.postal_code
        }
    }


@router.put("/", response_model=CustomerProfileResponseSchema)
async def update_profile(
    profile_data: CustomerProfileSchema,
    current_user: User = Depends(get_current_user)
):
    """Update customer profile (same as POST but explicit PUT)"""
    return await create_or_update_profile(profile_data, current_user)


@router.delete("/", status_code=status.HTTP_200_OK)
async def delete_profile(current_user: User = Depends(get_current_user)):
    """Delete customer profile (soft delete - clear data)"""
    profile = await CustomerProfile.filter(user=current_user).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Clear profile data (soft delete)
    profile.add1 = None
    profile.add2 = None
    profile.postal_code = None
    await profile.save()
    
    # Optionally clear user data
    current_user.name = None
    current_user.email = None
    current_user.photo = None
    await current_user.save()
    
    return {
        "success": True,
        "message": "Profile data cleared successfully"
    }


@router.delete("/hard-delete", status_code=status.HTTP_200_OK)
async def hard_delete_profile(current_user: User = Depends(get_current_user)):
    """Permanently delete customer profile"""
    profile = await CustomerProfile.filter(user=current_user).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Delete profile record
    await profile.delete()
    
    return {
        "success": True,
        "message": "Profile deleted permanently"
    }




"""
# # ==================== Dashboard Routes ====================

# dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# @dashboard_router.get("/stats/")
# async def get_dashboard_stats():
    ----# Get all dashboard statistics (Admin only)----
#     total_users = await User.all().count()
#     total_orders = await Order.all().count()
#     total_products = await Product.all().count()
    
#     return {
#         "success": True,
#         "message": "Dashboard statistics retrieved successfully",
#         "data": {
#             "total_users": total_users,
#             "total_orders": total_orders,
#             "total_products": total_products,
#             "total_revenue": 0.0  # Calculate from orders
#         }
#     }

# # ==================== Prescription Routes ====================

# prescription_router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


# @prescription_router.post("/", status_code=status.HTTP_201_CREATED)
# async def upload_prescription(prescription_data: PrescriptionUploadSchema):
#     ===Upload a prescription===
#     user = await User.filter(id=prescription_data.user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     prescription = await Prescription.create(
#         id=f"presc_{int(datetime.utcnow().timestamp())}",
#         user=user,
#         image_path=prescription_data.image_path,
#         file_name=prescription_data.file_name
#     )
    
#     return {
#         "success": True,
#         "message": "Prescription uploaded successfully",
#         "data": {
#             "id": prescription.id,
#             "user_id": prescription.user_id,
#             "image_path": prescription.image_path,
#             "file_name": prescription.file_name,
#             "status": prescription.status,
#             "uploaded_at": prescription.uploaded_at
#         }
#     }


# @prescription_router.get("/{prescription_id}/")
# async def get_prescription(prescription_id: str):
#     ===Get prescription with vendor responses===
#     prescription = await Prescription.filter(id=prescription_id).prefetch_related(
#         "vendor_responses"
#     ).first()
    
#     if not prescription:
#         raise HTTPException(status_code=404, detail="Prescription not found")
    
#     vendor_responses = await VendorResponse.filter(prescription=prescription).prefetch_related("medicines")
    
#     return {
#         "success": True,
#         "message": "Prescription retrieved successfully",
#         "data": {
#             "id": prescription.id,
#             "user_id": prescription.user_id,
#             "image_path": prescription.image_path,
#             "file_name": prescription.file_name,
#             "status": prescription.status,
#             "uploaded_at": prescription.uploaded_at,
#             "vendor_responses": [
#                 {
#                     "id": vr.id,
#                     "vendor_id": vr.vendor_id,
#                     "vendor_name": vr.vendor_name,
#                     "total_amount": float(vr.total_amount),
#                     "status": vr.status
#                 }
#                 for vr in vendor_responses
#             ]
#         }
#     }


"""