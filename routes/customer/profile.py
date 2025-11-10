from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
from applications.user.models import *
from applications.customer.models import *
from applications.customer.schemas import *
from applications.items.models import *
from applications.user.customer import CustomerProfile
# Import schemas
from app.token import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/")
async def get_profile(user_id: str = Query(...)):
    """Get user profile"""
    user = await User.filter(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "success": True,
        "message": "Profile retrieved successfully",
        "data": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "address_1": user.address_1,
            "address_2": user.address_2,
            "postal_code": user.postal_code
        }
    }


@router.put("/")
async def update_profile(user_id: str, profile_data: UserProfileUpdateSchema):
    """Update user profile"""
    user = await User.filter(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if profile_data.first_name:
        user.first_name = profile_data.first_name
    if profile_data.last_name:
        user.last_name = profile_data.last_name
    if profile_data.phone_number:
        user.phone_number = profile_data.phone_number
    if profile_data.address_1:
        user.address_1 = profile_data.address_1
    if profile_data.address_2:
        user.address_2 = profile_data.address_2
    if profile_data.postal_code:
        user.postal_code = profile_data.postal_code
    
    await user.save()
    
    return {
        "success": True,
        "message": "Profile updated successfully"
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