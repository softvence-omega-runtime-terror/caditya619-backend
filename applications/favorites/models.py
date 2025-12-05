# applications/favorites/models.py
from tortoise import fields, models


class CustomerFavoriteItem(models.Model):
    id = fields.IntField(pk=True)
    customer = fields.ForeignKeyField(
        "models.CustomerProfile",
        related_name="favorite_items",
        on_delete=fields.CASCADE
    )
    item = fields.ForeignKeyField(
        "models.Item",
        related_name="favorited_by",
        on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "customer_favorite_items"
        unique_together = (("customer", "item"),) 