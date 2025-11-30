from tortoise import fields, models
from tortoise.exceptions import ValidationError


class VendorProfile(models.Model):
    TYPE_CHOICES = (
        ("food", "Food"),
        ("grocery", "Grocery"),
        ("medicine", "Medicine"),
    )
    
    KYC_STATUS_CHOICES = (
        ("submitted", "Submitted"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    )
    
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="vendor_profile", on_delete=fields.CASCADE)
    owner_name = fields.CharField(max_length=255, null=True, blank=True)
    photo = fields.CharField(max_length=255, null=True, blank=True)
    type = fields.CharField(max_length=50, choices=TYPE_CHOICES, defaults='grocery')
    is_active = fields.BooleanField(default=True)
    
    latitude = fields.FloatField(null=True)
    longitude = fields.FloatField(null=True)

    nid = fields.CharField(max_length=60, null=True, blank=True)
    kyc_document = fields.CharField(max_length=500, null=True, blank=True)
    kyc_status = fields.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default=None, blank=True, null=True)

    open_time = fields.TimeField(null=True, blank=True)
    close_time = fields.TimeField(null=True, blank=True)

    class Meta:
        table = "vendor_profile"

    @property
    def is_completed(self) -> bool:
        common_required = [
            self.nid,
            self.latitude,
            self.longitude,
            self.photo,
            self.open_time,
            self.close_time,
        ]
        if not all(common_required):
            return False
        if self.type != "grocery" and not self.kyc_document:
            return False
        return True
        
        

class RestaurantProfile(models.Model):
    vendor = fields.OneToOneField("models.VendorProfile", related_name="restaurants", on_delete=fields.CASCADE)
    cuisines = fields.ManyToManyField("models.SubCategory", related_name="restaurants", blank=True, null=True)
    specialities = fields.CharField(max_length=100, null=True, blank=True)
    signature_dish = fields.ManyToManyField("models.Item", related_name="restaurants", blank=True, null=True)

    # async def save(self, *args, **kwargs):
    #     vendor_instance = await self.vendor
    #     if vendor_instance.type.lower() != "food":
    #         raise ValidationError(
    #             "Vendor type must be 'food' to create a RestaurantProfile."
    #         )
    #     await super().save(*args, **kwargs)

    class Meta:
        table = "restaurant_profiles"