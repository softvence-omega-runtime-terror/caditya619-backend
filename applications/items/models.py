from tortoise import fields, models
from app.utils.generate_unique import generate_unique
from datetime import datetime, timedelta, timezone


class Category(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    avatar = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    id = fields.IntField(pk=True)
    category = fields.ForeignKeyField("items.Category", related_name="subcategories", on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    avatar = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("category", "name"),)

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class SubSubCategory(models.Model):
    id = fields.IntField(pk=True)
    subcategory = fields.ForeignKeyField("items.SubCategory", related_name="sub_subcategories", on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    avatar = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("subcategory", "name"),)

    def __str__(self):
        return f"{self.subcategory.name} - {self.name}"


class ItemBase(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    slug = fields.CharField(max_length=255, unique=True)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = fields.DecimalField(max_digits=5, decimal_places=2, default=0.0)  # percentage discount
    box_price = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock = fields.IntField(default=0)

    # Extra flags
    popular = fields.BooleanField(default=False)
    free_delivery = fields.BooleanField(default=False)
    hot_deals = fields.BooleanField(default=False)
    flash_sale = fields.BooleanField(default=False)
    tag = fields.CharField(max_length=2000, null=True, default='academic_books')

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True
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
    def is_in_stock(self):
        return self.stock > 0

    @property
    def new_arrival(self):
        return datetime.now(timezone.utc) - self.created_at <= timedelta(days=3)

    @property
    def todays_deals(self):
        created_date = self.created_at.astimezone(timezone.utc).date()
        return self.hot_deals and created_date == datetime.now(timezone.utc).date()
    
    @property
    def discounted_price(self):
        return (self.price * self.discount) / 100

    @property
    def sell_price(self):
        return self.price - self.discounted_price

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
    
    async def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique(model=Item, field='slug', text=self.title)
        await super().save(*args, **kwargs)



class Item(ItemBase):
    pass

class ItemReview(models.Model):
    id = fields.IntField(pk=True)
    item = fields.ForeignKeyField("items.Item", related_name="reviews", on_delete=fields.CASCADE)
    user_id = fields.IntField()
    rating = fields.IntField()
    comment = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review of {self.item.title} by User {self.user_id}"