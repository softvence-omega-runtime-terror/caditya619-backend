# models/picture.py
from tortoise import fields
from tortoise.models import Model

class Picture(Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=200, index=True)
    description = fields.TextField(null=True)
    image_url = fields.CharField(max_length=500)
    thumbnail_url = fields.CharField(max_length=500, null=True)
    tags = fields.JSONField(default=list)
    category = fields.CharField(max_length=100, null=True, index=True)
    uploaded_by = fields.ForeignKeyField('models.User', related_name='pictures')
    is_active = fields.BooleanField(default=True, index=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pictures"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title}"