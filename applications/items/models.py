from datetime import datetime, timedelta, timezone

from tortoise import fields, models
from app.utils.generate_unique import generate_unique


class Category(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
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
    subcategory = fields.ForeignKeyField("models.SubCategory", related_name="sub_subcategories",
                                         on_delete=fields.CASCADE)
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
    title = fields.CharField(max_length=255)
    short_bio = fields.TextField(null=True)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = fields.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    tag = fields.CharField(max_length=2000, null=True, )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    # Computed properties
    @property
    def tags_list(self):
        if self.tag:
            return [tag.strip() for tag in self.tag.split(',')]
        return []

    @property
    def new_arrival(self):
        return datetime.now(timezone.utc) - self.created_at <= timedelta(days=3)

    @property
    def discounted_price(self):
        return round((self.price * self.discount) / 100, 2)

    @property
    def sell_price(self):
        return round(self.price - self.discounted_price, 2)

    def __str__(self) -> str:
        return self.title

    async def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = await generate_unique(model=self.__class__, field='slug', text=self.title)
        if self.discount < 0 or self.discount > 100:
            raise ValueError("Discount must be between 0 and 100.")
        await super().save(*args, **kwargs)


class ItemBase(models.Model):
    item = fields.ForeignKeyField("models.Item", on_delete=fields.CASCADE)
    box_price = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock = fields.IntField(default=0)
    total_sale = fields.IntField(default=0)

    popular = fields.BooleanField(default=False)
    free_delivery = fields.BooleanField(default=False)
    hot_deals = fields.BooleanField(default=False)
    flash_sale = fields.BooleanField(default=False)

    class Meta:
        abstract = True

    @property
    def is_in_stock(self):
        return self.stock > 0

    @property
    def today_deals(self):
        created_date = self.item.created_at.astimezone(timezone.utc).date()
        return self.hot_deals and created_date == datetime.now(timezone.utc).date()
