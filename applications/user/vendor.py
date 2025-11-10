from tortoise import fields, models



class VendorProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="vendor_profile", on_delete=fields.CASCADE)
    nid = fields.CharField(max_length=60)
    
    class Meta:
        table = "vendor_profile"
        