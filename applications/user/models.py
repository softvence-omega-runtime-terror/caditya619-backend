from tortoise import fields
from tortoise.models import Model
from passlib.hash import bcrypt
from app.utils.generate_unique import generate_unique


class Permission(Model):
    id = fields.IntField(pk=True, readonly=True, hidden=True)
    name = fields.CharField(max_length=100, unique=True, editable=False)
    codename = fields.CharField(max_length=100, unique=True, editable=False)

    def __str__(self):
        return f"{self.codename}"


class Group(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)

    permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "user.Permission", related_name="groups", through="group_permissions"
    )

    def __str__(self):
        return self.name


class User(Model):
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=100, null=True, unique=True)
    phone = fields.CharField(max_length=20, unique=True)
    username = fields.CharField(max_length=50, unique=True, blank=True, editable=True)
    name = fields.CharField(max_length=50, null=True, blank=True)

    is_rider = fields.BooleanField(default=False)
    is_vendor = fields.BooleanField(default=False)

    is_active = fields.BooleanField(default=True)
    is_staff = fields.BooleanField(default=False)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    groups: fields.ManyToManyRelation["Group"] = fields.ManyToManyField(
        "user.Group", related_name="users", through="user_groups"
    )

    user_permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "user.Permission", related_name="users", through="user_permissions"
    )

    async def has_permission(self, codename: str) -> bool:
        if self.is_superuser:
            return True

        await self.prefetch_related("user_permissions", "groups__permissions")

        if self.is_staff:
            for perm in self.user_permissions:
                if perm.codename == codename:
                    return True

            for group in self.groups:
                for perm in group.permissions:
                    if perm.codename == codename:
                        return True
        return False

    

    @classmethod
    def set_password(cls, password: str) -> str:
        return bcrypt.hash(password)

    def verify_password(self, password: str) -> bool:
        return bcrypt.verify(password, self.password_hash)



    class Meta:
        table = "users"

    def __str__(self):
        return f"{self.username} ({self.email})"
    
    async def save(self, *args, **kwargs):
        if not self.username:
            base_text = self.email or self.phone or "user"
            self.username = await generate_unique(
                model=User,
                field="username",
                text=base_text,
                max_length=20
            )
        await super().save(*args, **kwargs)


        # if is_new:
        #     from core.tasks import create_profile
        #     create_profile.delay(self.id)

    def __str__(self):
        return self.username
    

class Profile(Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("user.User", related_name="profile", on_delete=fields.CASCADE)
    first_name = fields.CharField(max_length=50, null=True, blank=True)
    last_name = fields.CharField(max_length=50, null=True, blank=True)
    bio = fields.TextField(null=True, blank=True)
    photo = fields.CharField(max_length=255, null=True, blank=True)
    banner = fields.CharField(max_length=255, null=True, blank=True)
    

    class Meta:
        table = "profiles"
