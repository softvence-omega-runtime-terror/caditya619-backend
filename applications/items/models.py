from datetime import datetime, timedelta, timezone

from tortoise import fields, models
from app.utils.generate_unique import generate_unique
from tortoise.validators import MinValueValidator, MaxValueValidator
from tortoise.expressions import Q
from tortoise.functions import Avg


class Category(models.Model):
    TYPE_CHOICES = (
        ("food", "Food"),
        ("groceries", "Groceries"),
        ("medicine", "Medicine"),
    )
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    type = fields.CharField(max_length=20, choices=TYPE_CHOICES, defaults='groceries')
    avatar = fields.CharField(max_length=500, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    id = fields.IntField(pk=True)
    category = fields.ForeignKeyField("models.Category", related_name="subcategories", on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    avatar = fields.CharField(max_length=500, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("category", "name"),)

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class SubSubCategory(models.Model):
    id = fields.IntField(pk=True)
    subcategory = fields.ForeignKeyField("models.SubCategory", related_name="sub_subcategories", on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    avatar = fields.CharField(max_length=500, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("subcategory", "name"),)

    def __str__(self):
        return f"{self.subcategory.name} - {self.name}"


class Item(models.Model):
    id = fields.IntField(pk=True)
    category = fields.ForeignKeyField("models.Category", related_name="item", on_delete=fields.CASCADE)
    subcategory = fields.ForeignKeyField("models.SubCategory", related_name="item", null=True, blank=True, on_delete=fields.SET_NULL)
    sub_subcategory = fields.ForeignKeyField("models.SubSubCategory", related_name="item", null=True, blank=True, on_delete=fields.SET_NULL)
    
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    image = fields.CharField(max_length=200, null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = fields.IntField(validators=[MinValueValidator(0), MaxValueValidator(5)], default=0)
    
    ratings = fields.FloatField(default=0.0)
    stock = fields.IntField(default=0)
    total_sale = fields.IntField(default=0)
    
    popular = fields.BooleanField(default=False)
    free_delivery = fields.BooleanField(default=False)
    hot_deals = fields.BooleanField(default=False)
    flash_sale = fields.BooleanField(default=False)
    
    weight = fields.FloatField(null=True)
    vendor = fields.ForeignKeyField("models.User", related_name='item', on_delete=fields.CASCADE)
    
    isOTC = fields.BooleanField(default=False)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    async def update_average_rating(self):
        from applications.items.review import ItemReview
        result = await ItemReview.filter(
            Q(item=self) & Q(parent__isnull=True) & Q(rating__not_isnull=True)
        ).aggregate(avg_rating=Avg("rating"))
        avg = round(result["avg_rating"] or 0.0, 2)
        self.ratings = avg
        await self.save(update_fields=["ratings"])

    async def get_total_reviews(self) -> int:
        from applications.items.review import ItemReview
        return await ItemReview.filter(item=self, parent=None).count()


    @property
    def is_in_stock(self):
        return self.stock > 0

    @property
    def new_arrival(self):
        return datetime.now(timezone.utc) - self.created_at <= timedelta(days=3)

    @property
    def today_deals(self):
        created_date = self.created_at.astimezone(timezone.utc).date()
        return self.hot_deals and created_date == datetime.now(timezone.utc).date()

    @property
    def discounted_price(self):
        return round((self.price * self.discount) / 100, 2)

    @property
    def sell_price(self):
        return round(self.price - self.discounted_price, 2)

    def __str__(self) -> str:
        return self.title


    
