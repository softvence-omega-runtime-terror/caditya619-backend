"""
applications.prescription.schemas.py
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class MedicineBase(BaseModel):
    name: str
    brand: Optional[str] = None
    dosage: Optional[str] = None
    quantity: int = 1
    price: Decimal
    notes: Optional[str] = None
    is_available: bool = True
    image_path: Optional[str] = None


class MedicineCreate(MedicineBase):
    item_id: Optional[int] = None


class MedicineResponse(MedicineBase):
    id: str
    vendor_id: str
    
    class Config:
        from_attributes = True


class VendorResponseBase(BaseModel):
    notes: Optional[str] = None


class VendorResponseCreate(VendorResponseBase):
    prescription_id: int
    medicines: List[MedicineCreate]


class VendorResponseUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    medicines: Optional[List[MedicineCreate]] = None


class VendorResponseSchema(VendorResponseBase):
    id: str
    prescription_id: str
    vendor_id: str
    vendor_name: str
    medicines: List[MedicineResponse]
    total_amount: Decimal
    status: str
    responded_at: datetime
    
    class Config:
        from_attributes = True


class PrescriptionCreate(BaseModel):
    image_path: str
    file_name: str
    notes: Optional[str] = None


class PrescriptionUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class PrescriptionResponse(BaseModel):
    id: str
    user_id: str
    image_path: str
    file_name: str
    uploaded_at: datetime
    status: str
    notes: Optional[str] = None
    vendor_responses: List[VendorResponseSchema] = []
    
    class Config:
        from_attributes = True


class PrescriptionListResponse(BaseModel):
    id: str
    user_id: str
    image_path: str
    file_name: str
    uploaded_at: datetime
    status: str
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True