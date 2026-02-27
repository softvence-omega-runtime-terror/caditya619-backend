from tortoise import fields
from tortoise.models import Model
import uuid
# -----------------------------
# User Settings
# -----------------------------
LANGUAGE_CHOICES = {
    "ENGLISH": "en",
    "FRENCH": "fr",
}

class UserSettings(Model):
    user  = fields.ForeignKeyField('models.User', on_delete=fields.CASCADE)  # Should reference users.id in your actual DB

    email_notifications = fields.BooleanField(default=False)
    push_notifications = fields.BooleanField(default=False)
    promotional_notifications = fields.BooleanField(default=False)
    parental_notifications = fields.BooleanField(default=False)
    user_activity_alerts = fields.BooleanField(default=False)

    language = fields.CharField(max_length=255, choices=LANGUAGE_CHOICES, default="ENGLISH")

    class Meta:
        table = "user_settings"


# -----------------------------
# Platform Settings
# -----------------------------
class PlatformSettings(Model):
    support_email = fields.CharField(max_length=255)
    admin_email = fields.CharField(max_length=255)

    allow_user_registration = fields.BooleanField(default=True)
    allow_business_registration = fields.BooleanField(default=True)

    class Meta:
        table = "platform_settings"
