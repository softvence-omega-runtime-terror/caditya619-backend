from tortoise import models, fields

class FreshChat(models.Model):
    user_id = fields.OneToOneField('models.User', on_delete=fields.CASCADE)
    restore_id = fields.CharField(max_length=400)

    def __str__(self):
        return f"{self.user_id} - {self.restore_id}"
