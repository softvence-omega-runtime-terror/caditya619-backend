from tortoise import models, fields

class FreshChat(models.Model):
    user = fields.OneToOneField(
        "models.User",  # User model reference
        on_delete=fields.CASCADE,
        related_name="freshchat"
    )
    restore_id = fields.CharField(max_length=400)

    def __str__(self):
        return f"{self.user_id} - {self.restore_id}"