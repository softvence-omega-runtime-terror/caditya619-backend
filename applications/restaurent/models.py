from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator
from typing import Optional
from tortoise.validators import MinValueValidator, MaxValueValidator

class SignatureDish(models.Model):
    """Signature Dishes for food vendors (restaurants)"""
    SPECIALTY_CHOICES = (
        ("food_biryani", "Biryani"),
        ("food_pizza", "Pizza"),
        ("food_burger", "Burger"),
        ("food_sandwich", "Sandwich"),
        ("food_pasta", "Pasta"),
        ("food_breads", "Breads"),
    )
    
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.User", related_name="signature_dishes", on_delete=fields.CASCADE)
    item = fields.ForeignKeyField("models.Item", related_name="as_signature_dish", on_delete=fields.CASCADE, null=True)
    name = fields.CharField(max_length=200)
    image = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    specialty_type = fields.CharField(max_length=50, choices=SPECIALTY_CHOICES)
    is_popular = fields.BooleanField(default=False)
    display_order = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "signature_dishes"
        ordering = ["display_order", "-is_popular"]


class VendorReview(models.Model):
    """Reviews for food vendors (restaurants) - Created by customers"""
    id = fields.IntField(pk=True)
    vendor = fields.ForeignKeyField("models.User", related_name="vendor_reviews", on_delete=fields.CASCADE)
    customer = fields.ForeignKeyField("models.User", related_name="customer_vendor_reviews", on_delete=fields.CASCADE)
    rating = fields.IntField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "vendor_reviews"
        unique_together = (("vendor", "customer"),)

    async def save(self, *args, **kwargs):
        """Auto-update vendor rating when customer creates/updates review"""
        await super().save(*args, **kwargs)
        # Import here to avoid circular imports
        from utils.vendor_rating_calculator import VendorRatingCalculator
        await VendorRatingCalculator.update_vendor_rating(self.vendor_id)
    
    async def delete(self, *args, **kwargs):
        """Auto-update vendor rating when customer deletes review"""
        vendor_id = self.vendor_id
        await super().delete(*args, **kwargs)
        # Import here to avoid circular imports
        from utils.vendor_rating_calculator import VendorRatingCalculator
        await VendorRatingCalculator.update_vendor_rating(vendor_id)


# Extension to existing VendorProfile model
# Add these fields to your existing VendorProfile model:
"""
class VendorProfile(models.Model):
    TYPE_CHOICES = (
        ("food", "Food"),
        ("grocery", "Grocery"),
        ("medicine", "Medicine"),
    )
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="vendor_profile", on_delete=fields.CASCADE)
    type = fields.CharField(max_length=20, choices=TYPE_CHOICES, defaults='grocery')
    nid = fields.CharField(max_length=60)
    
    # ADD THESE NEW FIELDS:
    business_name = fields.CharField(max_length=200, null=True)
    image = fields.CharField(max_length=500, null=True)
    delivery_time = fields.CharField(max_length=50, default="30-40 min")
    rating = fields.FloatField(default=0.0)
    address = fields.TextField(null=True)
    is_open = fields.BooleanField(default=True)
    cuisines = fields.JSONField(default=list)  # ["Italian", "Indian"]
    specialties = fields.JSONField(default=list)  # ["food_pizza", "food_pasta"]
    review_count = fields.IntField(default=0)
    popularity = fields.FloatField(default=0.0)
    is_top_rated = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
"""