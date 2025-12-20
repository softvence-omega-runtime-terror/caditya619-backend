from fastapi import APIRouter, HTTPException, Depends, Query
from tortoise.transactions import in_transaction
from pydantic import BaseModel
from typing import List, Optional
from routes.rider.notifications import send_notification, NotificationIn

from applications.prescription.models import (
    PrescriptionVendorResponse,
    PrescriptionMedicine,
    Prescription,
)
from applications.user.models import User
from applications.items.models import Item

from app.token import get_current_user
from app.auth import vendor_required


router = APIRouter(prefix="/prescriptions-order", tags=["Prescription Vendor Response"])


# ============================================================
#                   REQUEST SCHEMAS
# ============================================================

class MedicineInput(BaseModel):
    item_id: Optional[int] = None
    brand: Optional[str] = None
    dosage: Optional[str] = None
    quantity: int
    notes: Optional[str] = None
    is_available: bool = True


class VendorResponseInput(BaseModel):
    prescription_id: int
    notes: Optional[str] = None
    medicines: List[MedicineInput]


# ============================================================
#                   RESPONSE SERIALIZERS
# ============================================================

class MedicineSerializer(BaseModel):
    id: int
    item_id: Optional[int]
    name: str
    brand: Optional[str]
    dosage: Optional[str]
    quantity: int
    price: float
    notes: Optional[str]
    is_available: bool
    image_path: Optional[str]

    class Config:
        from_attributes = True


class VendorResponseSerializer(BaseModel):
    id: int
    vendor_id: int
    vendor_name: str
    vendor_email: str
    total_amount: float
    status: str
    notes: Optional[str]
    responded_at: str
    medicines: List[MedicineSerializer]

    class Config:
        from_attributes = True


class PrescriptionOrderSerializer(BaseModel):
    id: int
    user_id: int
    user_name: str
    image_path: str
    file_name: Optional[str]
    status: str
    notes: Optional[str]
    uploaded_at: str
    vendor_responses: List[VendorResponseSerializer]

    class Config:
        from_attributes = True




PRESCRIPTION_STATUS = {
    "underReview": "Prescription is currently under review by the staff",
    "valid": "Prescription is valid and approved",
    "invalid": "Prescription is invalid or rejected",
    "medicinesReady": "Medicines for the prescription are ready for delivery",
}
@router.put("/change-status/{prescription_id}", response_model=dict, dependencies=[Depends(vendor_required)])
async def change_prescription_status(
    prescription_id: int,
    status: str = Query(..., description="New status for the prescription ")
):
    """
        Change the status of a prescription.
        
        Available statuses:
        - underReview
        - valid
        - invalid
        - medicinesReady
    """
    if status not in PRESCRIPTION_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Available statuses: {list(PRESCRIPTION_STATUS.keys())}"
        )
    prescription = await Prescription.get_or_none(id=prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    prescription.status = status
    await prescription.save()

    try:
        if status == "underReview":
            await send_notification(NotificationIn(
                user_id=prescription.user_id,
                title="⏳ Prescription Under Review",
                body="A pharmacy has opened your prescription for review. You will be notified when medicines are available"
            ))
        elif status == "valid":
            await send_notification(NotificationIn(
                user_id=prescription.user_id,
                title="✅ Prescription Valid",
                body="Your prescription is valid. We are checking medicine availability."
            ))
        elif status == "invalid":
            await send_notification(NotificationIn(
                user_id=prescription.user_id,
                title="❌ Prescription Invalid",
                body="We could not validate your prescription. Please check and upload a valid one or contact support."
            ))
        elif status == "medicinesReady":
            await send_notification(NotificationIn(
                user_id=prescription.user_id,
                title="💊 Medicines Ready",
                body="Medicines are ready for your order. Review them now and place your order."
            ))
    except:
        print('Notification sending failed.')

    return {
        "status": "success",
        "message": f"Prescription status changed to '{status}'",
        "description": PRESCRIPTION_STATUS[status]
    }





# ============================================================
#                   CREATE ROUTE
# ============================================================

@router.post("/vendor-response", response_model=dict)
async def create_vendor_response(
    payload: VendorResponseInput,
    vendor: User = Depends(vendor_required)
):
    prescription = await Prescription.get_or_none(id=payload.prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Vendor cannot submit twice
    vendor_response = await PrescriptionVendorResponse.get_or_none(
        prescription=prescription,
        vendor=vendor
    )

    # Transaction Start
    async with in_transaction():
        if not vendor_response:
            vendor_response = await PrescriptionVendorResponse.create(
                prescription=prescription,
                vendor=vendor,
                total_amount=0,
                notes=payload.notes,
            )
        
        total_amount = 0  # calculate after creating medicines

        # Create Medicines
        for med in payload.medicines:
            item = await Item.get_or_none(id=med.item_id)
            if not item:
                continue

            # Use payload price if provided, else item's sell_price
            price = med.price if hasattr(med, "price") and med.price is not None else item.sell_price

            await PrescriptionMedicine.create(
                vendor_response=vendor_response,
                item_id=med.item_id,
                name=item.title,
                brand=med.brand,
                dosage=med.dosage,
                quantity=med.quantity,
                price=price,
                notes=med.notes,
                is_available=med.is_available,
                image_path=item.image,
            )

            # Add to total_amount
            total_amount += price * med.quantity

        # Update total_amount in vendor_response
        vendor_response.total_amount = total_amount
        prescription.status = "medicinesReady"
        await vendor_response.save()
        await prescription.save()
        await send_notification(NotificationIn(
            user_id=prescription.user_id,
            title="💊 Medicines Ready",
            body="Medicines are ready for your order. Review them now and place your order."
        ))

    # Build JSON Response
    await vendor_response.fetch_related("medicines")

    data = {
        "id": vendor_response.id,
        "prescription_id": vendor_response.prescription_id,
        "vendor_id": vendor_response.vendor_id,
        "total_amount": float(vendor_response.total_amount),
        "status": prescription.status,
        "notes": vendor_response.notes,
        "responded_at": vendor_response.responded_at,
        "medicines": [
            {
                "id": med.id,
                "item_id": med.item_id,
                "name": med.name,
                "brand": med.brand,
                "dosage": med.dosage,
                "quantity": med.quantity,
                "price": float(med.price),
                "notes": med.notes,
                "is_available": med.is_available,
                "image_path": med.image_path,
            }
            for med in vendor_response.medicines
        ]
    }

    return {
        "status": "success",
        "message": "Vendor response submitted successfully",
        "data": data
    }


# ============================================================
#                   GET FULL PRESCRIPTION ORDER
# ============================================================

@router.get(
    "/all",
    response_model=List[PrescriptionOrderSerializer],
    dependencies=[Depends(vendor_required)]
)
async def get_all_uploaded_prescriptions(
    status: Optional[str] = Query(
        None,
        description="Filter by status. e.g., 'uploaded', 'underReview', 'valid', 'invalid', 'medicinesReady'"
    )
):
    query = Prescription.all().order_by("-uploaded_at").prefetch_related("user", "vendor_responses__vendor", "vendor_responses__medicines")
    if status:
        query = query.filter(status=status)
    
    prescriptions = await query

    results = []

    for prescription in prescriptions:
        vendor_responses_data = []

        for vr in prescription.vendor_responses:
            medicines_list = [
                MedicineSerializer(
                    id=med.id,
                    item_id=med.item_id,
                    name=med.name,
                    brand=med.brand,
                    dosage=med.dosage,
                    quantity=med.quantity,
                    price=float(med.price),
                    notes=med.notes,
                    is_available=med.is_available,
                    image_path=med.image_path
                )
                for med in vr.medicines
            ]

            vendor_responses_data.append(
                VendorResponseSerializer(
                    id=vr.id,
                    vendor_id=vr.vendor_id,
                    vendor_name=vr.vendor.name,
                    vendor_email=vr.vendor.email,
                    total_amount=float(vr.total_amount),
                    status=vr.status,
                    notes=vr.notes,
                    responded_at=vr.responded_at.isoformat() if vr.responded_at else None,
                    medicines=medicines_list
                )
            )

        results.append(
            PrescriptionOrderSerializer(
                id=prescription.id,
                user_id=prescription.user.id,
                user_name=prescription.user.name,
                image_path=prescription.image_path,
                file_name=prescription.file_name,
                status=prescription.status,
                notes=prescription.notes,
                uploaded_at=prescription.uploaded_at.isoformat(),
                vendor_responses=vendor_responses_data,
            )
        )

    return results



@router.get("/{prescription_id}", response_model=PrescriptionOrderSerializer, dependencies=[Depends(vendor_required)])
async def get_prescription_order(
    prescription_id: int
):
    prescription = await Prescription.get_or_none(id=prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    await prescription.fetch_related("user", "vendor_responses")

    vendor_responses_data = []

    for vr in prescription.vendor_responses:
        await vr.fetch_related("vendor", "medicines")

        medicines_list = [
            MedicineSerializer(
                id=med.id,
                item_id=med.item_id,
                name=med.name,
                brand=med.brand,
                dosage=med.dosage,
                quantity=med.quantity,
                price=float(med.price),
                notes=med.notes,
                is_available=med.is_available,
                image_path=med.image_path
            )
            for med in vr.medicines
        ]

        vendor_responses_data.append(
            VendorResponseSerializer(
                id=vr.id,
                vendor_id=vr.vendor_id,
                vendor_name=vr.vendor.name,
                vendor_email=vr.vendor.email,
                total_amount=float(vr.total_amount),
                status=vr.status,
                notes=vr.notes,
                responded_at=str(vr.responded_at),
                medicines=medicines_list
            )
        )

    return PrescriptionOrderSerializer(
        id=prescription.id,
        user_id=prescription.user.id,
        user_name=prescription.user.name,
        image_path=prescription.image_path,
        file_name=prescription.file_name,
        status=prescription.status,
        notes=prescription.notes,
        uploaded_at=str(prescription.uploaded_at),
        vendor_responses=vendor_responses_data,
    )
