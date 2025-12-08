from tortoise import fields
from tortoise.models import Model
from datetime import datetime


class ChatMessage(Model):
    """Store all chat messages persistently"""
    id = fields.IntField(pk=True)
    
    # Sender info
    from_type = fields.CharField(max_length=20)  # "riders", "customers", "vendors", "admins"
    from_id = fields.CharField(max_length=100)   # User ID
    from_name = fields.CharField(max_length=255, null=True)  # Display name
    
    # Recipient info
    to_type = fields.CharField(max_length=20)
    to_id = fields.CharField(max_length=100)
    
    # Message content
    text = fields.TextField()
    message_id = fields.CharField(max_length=100, unique=True)  # UUID for idempotency
    
    # Status tracking
    is_read = fields.BooleanField(default=False)
    is_delivered = fields.BooleanField(default=False)
    
    # Metadata
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "chat_messages"
        indexes = [
            ["from_type", "from_id", "to_type", "to_id", "created_at"],
            ["to_type", "to_id", "is_read"],
        ]
    
    def __str__(self):
        return f"{self.from_type}:{self.from_id} -> {self.to_type}:{self.to_id}: {self.text[:50]}"


class ChatSession(Model):
    """Track active chat sessions between users"""
    id = fields.IntField(pk=True)
    
    # User 1
    user1_type = fields.CharField(max_length=20)
    user1_id = fields.CharField(max_length=100)
    
    # User 2
    user2_type = fields.CharField(max_length=20)
    user2_id = fields.CharField(max_length=100)
    
    # Session state
    is_active = fields.BooleanField(default=True)
    last_message_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    ended_at = fields.DatetimeField(null=True)
    
    class Meta:
        table = "chat_sessions"
        unique_together = [["user1_type", "user1_id", "user2_type", "user2_id"]]
        indexes = [
            ["user1_type", "user1_id", "is_active"],
            ["user2_type", "user2_id", "is_active"],
        ]


class OfflineNotification(Model):
    """Store notifications for offline users"""
    id = fields.IntField(pk=True)
    
    # Recipient
    to_type = fields.CharField(max_length=20)
    to_id = fields.CharField(max_length=100)
    
    # Notification content
    notification_id = fields.CharField(max_length=100, unique=True)
    title = fields.CharField(max_length=255)
    body = fields.TextField()
    
    # Metadata
    data = fields.JSONField(default={})
    urgency = fields.CharField(max_length=20, default="normal")  # low, normal, high, critical
    
    # Status
    is_delivered = fields.BooleanField(default=False)
    delivered_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()  # Auto-delete after 30 days
    
    class Meta:
        table = "offline_notifications"
        indexes = [
            ["to_type", "to_id", "is_delivered"],
            ["expires_at"],
        ]


class LocationHistory(Model):
    """Store location updates for offline users and analytics"""
    id = fields.IntField(pk=True)
    
    # Rider location
    rider_type = fields.CharField(max_length=20, default="riders")
    rider_id = fields.CharField(max_length=100)
    
    # Location coordinates
    latitude = fields.DecimalField(max_digits=9, decimal_places=6)
    longitude = fields.DecimalField(max_digits=9, decimal_places=6)
    
    # Additional data
    accuracy = fields.FloatField(null=True)
    speed = fields.FloatField(null=True)
    heading = fields.FloatField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()  # Keep for 24 hours only
    
    class Meta:
        table = "location_history"
        indexes = [
            ["rider_id", "created_at"],
        ]