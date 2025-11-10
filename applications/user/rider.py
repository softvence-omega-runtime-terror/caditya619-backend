from tortoise import fields, models

class RiderProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="rider_profile", on_delete=fields.CASCADE)
    driving_license = fields.CharField(max_length=100)
    nid = fields.CharField(max_length=60)
    
    class Meta:
        table = "rider_profile"
        