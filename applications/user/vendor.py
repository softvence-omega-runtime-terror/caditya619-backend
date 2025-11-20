from tortoise import fields, models


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
    owner_name = fields.CharField(max_length=100, null=True, blank=True)
    type = fields.CharField(max_length=20, choices=TYPE_CHOICES, defaults='grocery')
    photo = fields.CharField(max_length=255, null=True, blank=True)
    is_active = fields.BooleanField(default=True)
    
    latitude = fields.FloatField(null=True)
    longitude = fields.FloatField(null=True)

    nid = fields.CharField(max_length=60, null=True, blank=True)
    fassai = fields.CharField(max_length=100, null=True, blank=True)
    drug_license = fields.CharField(max_length=100, null=True, blank=True)
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
        if self.type == "food" and not self.fassai:
            return False
        if self.type == "medicine" and not self.drug_license:
            return False
        return True
        
        
