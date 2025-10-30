from fastapi import APIRouter, HTTPException, status, Depends, Form, Query, Body, UploadFile, File
from typing import List, Optional
from app.auth import *
from applications.user.models import User, Permission, Group, CustomerProfile, VendorProfile, RiderProfile
from app.utils.otp_manager import verify_otp
from app.utils.file_manager import save_file, update_file, delete_file

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['User'])



@router.get("/users", dependencies=[
        Depends(login_required),
        Depends(permission_required("view_user")),
    ]
)
async def get_all_users():
    return await User.all().values(
        "id", "phone", "email", "is_active", "is_rider", "is_vendor", "is_staff", "is_superuser", "created_at", "updated_at"
    )


@router.get(
    "/users/{user_id}",
    dependencies=[
        Depends(login_required),
    ]
)
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    user = await User.get_or_none(id=user_id).prefetch_related("groups", "user_permissions")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.is_rider or current_user.is_vendor:
        if current_user.id != user.id:
            return {
                "id": user.id,
                "phone": user.phone,
                "email": user.email,
                "created_at": user.created_at,
            }

    groups = [group.name for group in await user.groups.all()]
    user_perms = [perm.codename for perm in await user.user_permissions.all()]

    group_perms = []
    if current_user.is_superuser or current_user.id == user.id:
        for group in await user.groups.all():
            perms = await group.permissions.all()
            group_perms.extend([perm.codename for perm in perms])

    all_perms = list(set(user_perms + group_perms))

    return {
        "id": user.id,
        "email": user.email,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "groups": groups,
        "permissions": all_perms,
    }



@router.put("/{user_id}", dependencies=[Depends(login_required)])
async def update_user(
    user_id: int,
    phone: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
    add1: Optional[str] = None,
    add2: Optional[str] = None,
    postal_code: Optional[str] = None,
    driving_license: Optional[str] = None,
    nid: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_staff: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    group_ids: Optional[List[int]] = None,
    permission_ids: Optional[List[int]] = None,
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    user = await User.get_or_none(id=user_id).prefetch_related("groups", "user_permissions")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_superuser and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot update a superuser account.",
        )

    if current_user.id != user.id:
        has_perm = await current_user.has_permission("update_user")
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this user.",
            )

    sensitive_fields = [is_active, is_staff, is_superuser, group_ids, permission_ids]
    if any(v is not None for v in sensitive_fields):
        has_perm = await current_user.has_permission("update_user")
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not allowed to update these fields.",
            )

    if email:
        email_exists = await User.filter(email=email).exclude(id=user.id).exists()
        if email_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already in use.",
            )
        user.email = email

    if phone:
        if not otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP is required to update phone number.",
            )
        verified = await verify_otp(phone, otp, purpose="update_user_data")
        if not verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP not verified.",
            )
        user.phone = phone

    if is_active is not None:
        user.is_active = is_active
    if is_staff is not None:
        user.is_staff = is_staff
    if is_superuser is not None:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superuser can modify superuser status.",
            )
        user.is_superuser = is_superuser

    if photo is not None:
        photo_path = await update_file(photo, user.photo, upload_to='user_photo', allowed_extensions=['jpg', 'png', 'jpeg', 'webp'])
        user.photo = photo_path
    await user.save()

    if any([add1, add2, postal_code]):
        profile, _ = await CustomerProfile.get_or_create(user=user)
        if add1 is not None:
            profile.add1 = add1
        if add2 is not None:
            profile.add2 = add2
        if postal_code is not None:
            profile.postal_code = postal_code
        await profile.save()

    if user.is_rider:
        rider_profile, _ = await RiderProfile.get_or_create(
            user=user, defaults={"driving_license": "", "nid": ""}
        )
        if driving_license:
            rider_profile.driving_license = driving_license
        if nid:
            rider_profile.nid = nid
        await rider_profile.save()

    if user.is_vendor:
        vendor_profile, _ = await VendorProfile.get_or_create(
            user=user, defaults={"nid": ""}
        )
        if nid:
            vendor_profile.nid = nid
        await vendor_profile.save()

    if group_ids is not None:
        groups = await Group.filter(id__in=group_ids)
        await user.groups.clear()
        await user.groups.add(*groups)

    if permission_ids is not None:
        permissions = await Permission.filter(id__in=permission_ids)
        await user.user_permissions.clear()
        await user.user_permissions.add(*permissions)

    user_data = {
        "id": user.id,
        "phone": user.phone,
        "email": user.email,
        "is_active": user.is_active,
        "is_rider": user.is_rider,
        "is_vendor": user.is_vendor,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "groups": [g.id for g in await user.groups.all()],
        "permissions": [p.id for p in await user.user_permissions.all()],
    }

    return {
        "message": "User updated successfully",
        "user": user_data,
    }



@router.delete("/users/{user_id}", dependencies=[
        Depends(login_required),
        Depends(permission_required("delete_user")),
    ]
)
async def delete_user(user_id: int):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await delete_file(user.photo)
    await user.delete()
    return {"detail": "User deleted successfully"}












