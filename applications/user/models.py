from tortoise import fields
from tortoise.exceptions import IntegrityError
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
        "models.Permission", related_name="groups", through="group_permissions"
    )

    def __str__(self):
        return self.name


class User(Model):
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=100, null=True, unique=True)
    phone = fields.CharField(max_length=20, unique=True)
    name = fields.CharField(max_length=50, null=True, blank=True)
    photo = fields.CharField(max_length=255, null=True, blank=True)

    is_rider = fields.BooleanField(default=False)
    is_vendor = fields.BooleanField(default=False)

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

        if self.is_staff:
            for perm in self.user_permissions:
                if perm.codename == codename:
                    return True

            for group in self.groups:
                for perm in group.permissions:
                    if perm.codename == codename:
                        return True
        return False

    
    class Meta:
        table = "users"

    def __str__(self):
        return f"({self.phone})"
    
    async def save(self, *args, **kwargs):
        await super().save(*args, **kwargs)

    

class CustomerProfile(Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="customer_profile", on_delete=fields.CASCADE)
    add1 = fields.CharField(max_length=100, null=True, blank=True)
    add2 = fields.CharField(max_length=100, null=True, blank=True)
    postal_code = fields.CharField(max_length=20, null=True, blank=True)

    class Meta:
        table = "cus_profile"
    
    async def save(self, *args, **kwargs):
        if not self.user:
            raise IntegrityError("CustomerProfile must be associated with a User before saving.")
        await super().save(*args, **kwargs)
        

class RiderProfile(Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="rider_profile", on_delete=fields.CASCADE)
    driving_license = fields.CharField(max_length=100)
    nid = fields.CharField(max_length=60)
    
    class Meta:
        table = "rider_profile"
        
    async def save(self, *args, **kwargs):
        if not self.user:
            raise IntegrityError("RiderProfile must be associated with a User.")
        if not self.user.is_rider:
            raise IntegrityError("User must be marked as a rider to create RiderProfile.")
        await super().save(*args, **kwargs)

class VendorProfile(Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="vendor_profile", on_delete=fields.CASCADE)
    nid = fields.CharField(max_length=60)
    
    class Meta:
        table = "vendor_profile"
        
    async def save(self, *args, **kwargs):
        if not self.user:
            raise IntegrityError("RiderProfile must be associated with a User.")
        if not self.user.is_vendor:
            raise IntegrityError("User must be marked as a vendor to create VendorProfile.")
        await super().save(*args, **kwargs)
