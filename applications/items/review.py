from tortoise import fields, models
from tortoise.validators import MinValueValidator, MaxValueValidator


class ItemReview(models.Model):
    id = fields.IntField(pk=True)
    item = fields.ForeignKeyField("models.Item", related_name="reviews", on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', on_delete=fields.CASCADE, related_name='reviewer')
    rating = fields.IntField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = fields.TextField(null=True)
    parent = fields.ForeignKeyField('models.ItemReview', null=True, blank=True, related_name="replies", on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_reply(self):
        return self.parent is not None

    def __str__(self):
        return f"Review of {self.item.title} by User {self.user.email}"
