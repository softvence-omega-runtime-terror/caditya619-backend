from tortoise import fields, models


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
    
    latitude = fields.FloatField(null=True)
    longitude = fields.FloatField(null=True)
    
    fassai = fields.CharField(max_length=100, null=True, blank=True)
    drug_license = fields.CharField(max_length=100, null=True, blank=True)
    is_varified = fields.BooleanField(defaults=False)
    class Meta:
        table = "vendor_profile"
        