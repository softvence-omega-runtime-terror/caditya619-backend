from tortoise import fields, models
from tortoise.exceptions import ValidationError
from decimal import Decimal


class StoreDetails(models.Model):
    id = fields.IntField(pk=True)
    location = fields.CharField(max_length=300, default="Dhaka")
    home_delivery = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50.00"))
    courier = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("45.00"))
    standard_delivery = fields.IntField(default=5)
    cost_per_kg = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("20.00"))
    home_extra_charge = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    same_city = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    different_city = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    outside_dhaka = fields.DecimalField(max_digits=10, decimal_places=2, default=Decimal("20.00"))
    vat = fields.FloatField(default=0.0)
    cod_available = fields.BooleanField(default=True)
    bkash_no = fields.CharField(max_length=12, null=True)
    nagad_no = fields.CharField(max_length=12, null=True)
    rocket_no = fields.CharField(max_length=12, null=True)
    bank_ac = fields.CharField(max_length=50, null=True)
    bank_name = fields.CharField(max_length=100, null=True)
    bank_branch = fields.CharField(max_length=100, null=True)

    class Meta:
        table = "store_details"

    async def save(self, *args, **kwargs):
        if not self.pk:
            existing = await StoreDetails.exists()
            if existing:
                raise ValidationError("Only one StoreDetails object is allowed.")
        await super().save(*args, **kwargs)

    async def get_shipping_cost(self, method: str, is_cod: bool = False) -> Decimal:
        cost = Decimal("0")
        if method == "home_delivery":
            cost = self.home_delivery
        elif method == "courier":
            cost = self.courier

        if is_cod and self.cod_available:
            cost += self.home_extra_charge
        return cost
