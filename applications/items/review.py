from tortoise import fields, models
from tortoise.validators import MinValueValidator, MaxValueValidator


class ItemReview(models.Model):
    id = fields.IntField(pk=True)
    item = fields.ForeignKeyField("models.Item", related_name="reviews", on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', on_delete=fields.CASCADE, related_name='item_reviews') 
    rating = fields.IntField(validators=[MinValueValidator(1), MaxValueValidator(5)], null=True)
    comment = fields.TextField(null=True)
    parent = fields.ForeignKeyField('models.ItemReview', null=True, related_name="replier", on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


    class Meta:
        ordering = ["-created_at"]

    @property
    def is_reply(self):
        return self.parent is not None

    def __str__(self):
        return f"Review of {self.item.title} by User {self.user.email}"
    
    async def save(self, *args, **kwargs):
        if self.is_reply and self.rating:
            raise ValueError("Replier can't give ratings")
        await super().save(*args, **kwargs)
        if not self.is_reply:
            await self.item.update_average_rating()

    async def delete(self, *args, **kwargs):
        item = self.item
        await super().delete(*args, **kwargs)
        if not self.is_reply:
            await item.update_average_rating()
