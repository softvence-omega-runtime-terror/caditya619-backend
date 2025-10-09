from tortoise import fields
from tortoise.models import Model
from passlib.hash import bcrypt


class Permission(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True, editable=False)
    codename = fields.CharField(max_length=100, unique=True, editable=False)

    def __str__(self):
        return f"{self.codename}"


class Group(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)

    permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "models.Permission", related_name="groups", through="group_permissions"
    )

    def __str__(self):
        return self.name
    

class User(Model):
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=100, null=True, unique=True)
    phone = fields.CharField(max_length=20, null=True, unique=True)
    username = fields.CharField(max_length=50, unique=True, blank=True, editable=True)
    password = fields.CharField(max_length=128)
    is_active = fields.BooleanField(default=True)
    is_staff = fields.BooleanField(default=False)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    groups: fields.ManyToManyRelation["Group"] = fields.ManyToManyField(
        "models.Group", related_name="users", through="user_groups"
    )

    user_permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "models.Permission", related_name="users", through="user_permissions"
    )
    
    async def has_permission(self, codename: str) -> bool:
        if self.is_superuser:
            return True

        await self.prefetch_related("user_permissions", "groups__permissions")

        for perm in self.user_permissions:
            if perm.codename == codename:
                return True

        for group in self.groups:
            for perm in group.permissions:
                if perm.codename == codename:
                    return True

        return False

    

    @classmethod
    def hash_password(cls, password: str) -> str:
        return bcrypt.hash(password)

    def verify_password(self, password: str) -> bool:
        return bcrypt.verify(password, self.password_hash)



    class Meta:
        table = "users"

    def __str__(self):
        return f"{self.username} ({self.email})"
    
    async def save(self, *args, **kwargs):
        from app.utils import generate_unique
        if not self.username:
            self.username = await generate_unique(self.email or self.phone or "user", User)
        await super().save(*args, **kwargs)


        # if is_new:
        #     from core.tasks import create_profile
        #     create_profile.delay(self.id)

    def __str__(self):
        return self.username
    
    
from datetime import datetime, timedelta, timezone
class TemporaryOTP(Model):
    id = fields.IntField(pk=True)
    user_key = fields.CharField(max_length=300, unique=True)
    otp = fields.CharField(max_length=6)
    created_at = fields.DatetimeField(auto_now=True)
    
    @property
    def is_valid(self) -> bool:
        """Check if OTP is still valid (5 minutes)."""
        return self.created_at + timedelta(minutes=5) > datetime.now(timezone.utc)

    async def delete_if_expired(self):
        """Delete the OTP if expired."""
        if not self.is_valid:
            await self.delete()

    def __str__(self):
        expires_at = self.created_at + timedelta(minutes=5)
        remaining_time = (expires_at - datetime.now(timezone.utc)).seconds
        return f"OTP for {self.user_key}, expires in {remaining_time} seconds."

    async def save(self, *args, **kwargs):
        """Delete expired OTPs before saving a new one."""
        expire_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        await TemporaryOTP.filter(created_at__lte=expire_time).delete()
        await super().save(*args, **kwargs)