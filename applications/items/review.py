from tortoise import fields, models
from tortoise.validators import MinValueValidator, MaxValueValidator


class ItemReview(models.Model):
    id = fields.IntField(pk=True)
    item = fields.ForeignKeyField("models.Item", related_name="reviews", on_delete=fields.CASCADE)
    user = fields.ForeignKeyField("models.User", related_name="item_reviews", on_delete=fields.CASCADE)
    rating = fields.IntField(validators=[MinValueValidator(1), MaxValueValidator(5)], null=True)
    comment = fields.TextField(null=True)
    parent = fields.ForeignKeyField("models.ItemReview", related_name="replies", null=True, on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_reply(self):
        return self.parent_id is not None

    def __str__(self):
        return f"Review of {self.item_id} by User {self.user_id}"

    async def update_average_rating(self):
        from tortoise.functions import Avg
        from applications.items.review import ItemReview
        qs = ItemReview.filter(item_id=self.id, parent_id__isnull=True, rating__not_isnull=True)
        result = await qs.annotate(avg_rating=Avg("rating")).first()
        avg = round(result.avg_rating or 0.0, 2) if result else 0.0

        self.ratings = avg
        await self.save(update_fields=["ratings"])

    async def delete(self, *args, **kwargs):
        item = await self.item
        await super().delete(*args, **kwargs)
        if not self.is_reply:
            await item.update_average_rating()