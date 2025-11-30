"""
applications.prescription.models.py
"""
from tortoise import fields
from tortoise.models import Model
from datetime import datetime, timezone


class Prescription(Model):
    """Customer prescription uploads"""
    
    STATUS_CHOICES = (
        ("uploaded", "Uploaded"),
        ("underReview", "Under Review"),
        ("valid", "Valid"),
        ("invalid", "Invalid"),
        ("medicinesReady", "Medicines Ready"),
    )
    
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", 
        related_name="prescriptions", 
        on_delete=fields.CASCADE
    )
    image_path = fields.CharField(max_length=500)
    file_name = fields.CharField(max_length=255)
    uploaded_at = fields.DatetimeField(auto_now_add=True)
    status = fields.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default="uploaded"
    )
    notes = fields.TextField(null=True, blank=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "prescriptions"


class PrescriptionVendorResponse(Model):
    """Vendor responses to prescriptions"""
    
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("partiallyApproved", "Partially Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    )
    
    id = fields.IntField(pk=True)
    prescription = fields.ForeignKeyField(
        "models.Prescription",
        related_name="vendor_responses",
        on_delete=fields.CASCADE
    )
    vendor = fields.ForeignKeyField(
        "models.User",
        related_name="prescription_responses",
        on_delete=fields.CASCADE
    )
    total_amount = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = fields.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    responded_at = fields.DatetimeField(auto_now_add=True)
    notes = fields.TextField(null=True, blank=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "prescription_vendor_responses"
        unique_together = (("prescription", "vendor"),)


class PrescriptionMedicine(Model):
    """Medicines in vendor responses"""
    
    id = fields.IntField(pk=True)
    vendor_response = fields.ForeignKeyField(
        "models.PrescriptionVendorResponse",
        related_name="medicines",
        on_delete=fields.CASCADE
    )
    item = fields.ForeignKeyField(
        "models.Item",
        related_name="prescription_medicines",
        on_delete=fields.SET_NULL,
        null=True,
        blank=True
    )
    name = fields.CharField(max_length=255)
    brand = fields.CharField(max_length=255, null=True, blank=True)
    dosage = fields.CharField(max_length=100, null=True, blank=True)
    quantity = fields.IntField(default=1)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    notes = fields.TextField(null=True, blank=True)
    is_available = fields.BooleanField(default=True)
    image_path = fields.CharField(max_length=500, null=True, blank=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "prescription_medicines"