"""
applications.prescription.routes.py
"""
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from typing import List, Optional
from decimal import Decimal
from app.utils.file_manager import save_file
from applications.prescription.schemas import (
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUpdate,
    PrescriptionListResponse,
    VendorResponseCreate,
    VendorResponseSchema,
    VendorResponseUpdate
)
from applications.prescription.models import Prescription, PrescriptionVendorResponse, PrescriptionMedicine
from applications.user.models import User
from applications.user.vendor import VendorProfile
from app.token import get_current_user
router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


async def get_current_vendor():
    # Replace with your actual vendor authentication logic
    pass


# ============== CUSTOMER ENDPOINTS ==============

@router.post("/", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    image_path: UploadFile = File(...),
    file_name: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Customer uploads a prescription image
    """
    if not image_path or not image_path.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file is required"
        )
    
    saved_image_path = await save_file(image_path, upload_to="category_avatars")

    try:
        prescription = await Prescription.create(
            user=current_user,
            image_path=saved_image_path,
            file_name=file_name,
            notes=notes,
            status="uploaded"
        )
        
        return await format_prescription_response(prescription)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating prescription: {str(e)}"
        )


@router.get("/", response_model=List[PrescriptionListResponse])
async def get_user_prescriptions(
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = None
):
    """
    Get all prescriptions for the current user
    """
    query = Prescription.filter(user=current_user)
    
    if status_filter:
        query = query.filter(status=status_filter)
    
    prescriptions = await query.order_by('-uploaded_at').all()
    
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "image_path": p.image_path,
            "file_name": p.file_name,
            "uploaded_at": p.uploaded_at,
            "status": p.status,
            "notes": p.notes
        }
        for p in prescriptions
    ]


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription_detail(
    prescription_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed prescription with all vendor responses
    """
    prescription = await Prescription.filter(
        id=prescription_id,
        user=current_user
    ).prefetch_related(
        'vendor_responses__vendor__vendor_profile',
        'vendor_responses__medicines'
    ).first()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    return await format_prescription_response(prescription)


# @router.patch("/{prescription_id}", response_model=PrescriptionResponse)
# async def update_prescription(
#     prescription_id: int,
#     prescription_update: PrescriptionUpdate,
#     current_user: User = Depends(get_current_user)
# ):
#     """
#     Update prescription status or notes
#     """
#     prescription = await Prescription.filter(
#         id=prescription_id,
#         user=current_user
#     ).first()
    
#     if not prescription:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Prescription not found"
#         )
    
#     if prescription_update.status:
#         prescription.status = prescription_update.status
#     if prescription_update.notes is not None:
#         prescription.notes = prescription_update.notes
    
#     await prescription.save()
    
#     return await format_prescription_response(prescription)


@router.delete("/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription(
    prescription_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a prescription
    """
    prescription = await Prescription.filter(
        id=prescription_id,
        user=current_user
    ).first()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    await prescription.delete()
    return None




# ============== HELPER FUNCTIONS ==============

async def format_prescription_response(prescription: Prescription) -> dict:
    """Format prescription with vendor responses"""
    vendor_responses = await PrescriptionVendorResponse.filter(
        prescription=prescription
    ).prefetch_related('vendor__vendor_profile', 'medicines').all()
    
    formatted_responses = [await format_vendor_response(vr) for vr in vendor_responses]
    
    return {
        "id": str(prescription.id),
        "user_id": str(prescription.user_id),
        "image_path": prescription.image_path,
        "file_name": prescription.file_name,
        "uploaded_at": prescription.uploaded_at,
        "status": prescription.status,
        "notes": prescription.notes,
        "vendor_responses": formatted_responses
    }


async def format_vendor_response(vendor_response: PrescriptionVendorResponse) -> dict:
    """Format vendor response with medicines"""
    vendor = await vendor_response.vendor
    vendor_profile = await VendorProfile.filter(user=vendor).first()
    vendor_name = vendor_profile.business_name if vendor_profile and hasattr(vendor_profile, 'business_name') else f"Vendor {vendor.id}"
    
    medicines = await PrescriptionMedicine.filter(vendor_response=vendor_response).all()
    
    formatted_medicines = [
        {
            "id": str(m.item_id),
            "name": m.name,
            "brand": m.brand,
            "dosage": m.dosage,
            "quantity": m.quantity,
            "price": float(m.price),
            "notes": m.notes,
            "is_available": m.is_available,
            "image_path": m.image_path,
            "vendor_id": str(vendor_response.vendor_id)
        }
        for m in medicines
    ]
    
    return {
        "id": str(vendor_response.id),
        "prescription_id": str(vendor_response.prescription_id),
        "vendor_id": str(vendor_response.vendor_id),
        "vendor_name": vendor_name,
        "medicines": formatted_medicines,
        "total_amount": float(vendor_response.total_amount),
        "status": vendor_response.status,
        "responded_at": vendor_response.responded_at,
        "notes": vendor_response.notes
    }