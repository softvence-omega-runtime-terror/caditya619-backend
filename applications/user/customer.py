from tortoise import fields, models


class CustomerProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="customer_profile", on_delete=fields.CASCADE)
    add1 = fields.CharField(max_length=100, null=True, blank=True)
    add2 = fields.CharField(max_length=100, null=True, blank=True)
    postal_code = fields.CharField(max_length=20, null=True, blank=True)

    class Meta:
        table = "cus_profile"
    
        