from tortoise import fields, models



# class DiscountCode(models.Model):
#     id = fields.IntField(pk=True)
#     code = fields.CharField(max_length=50, unique=True)
#     description = fields.TextField(null=True)
#     discount_amount = fields.DecimalField(max_digits=10, decimal_places=2)
#     is_active = fields.BooleanField(default=True)
#     created_at = fields.DatetimeField(auto_now_add=True)
#     updated_at = fields.DatetimeField(auto_now=True)

#     class Meta:
#         table = "discount_code"