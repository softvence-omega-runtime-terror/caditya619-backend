from fastapi import APIRouter, HTTPException, status, Depends, Form, Query, Body
from typing import List, Optional
from app.auth import *
from applications.user.models import User, Permission, Group

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['User'])


# ------------------------------------------------------------------------
@router.post(
    "/users",
    # dependencies=[
    #     Depends(login_required),
    #     Depends(staff_required),  # ensures only staff/superuser can create
    # ]
)
async def create_user(
    username: str = Form(..., description="Username"),
    email: str = Form(..., description="Email"),
    password: str = Form(..., min_length=8, description="User password", example="********"),
    is_active: bool = Form(True),
    is_staff: bool = Form(False),
    is_superuser: bool = Form(False),
    # current_user: User = Depends(get_current_user),
):
    # --- PERMISSION LOGIC ---
    # if not current_user.is_superuser and is_superuser:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Staff users cannot create superusers."
    #     )

    # --- CHECK DUPLICATES ---
    if await User.filter(email=email).exists():
        raise HTTPException(status_code=400, detail="Email already registered")
    if await User.filter(username=username).exists():
        raise HTTPException(status_code=400, detail="Username already registered")

    # --- CREATE USER ---
    hashed_password = pwd_context.hash(password)
    new_user = await User.create(
        username=username,
        email=email,
        password=hashed_password,
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser
    )

    return {
        "detail": "User created successfully",
        "new_user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "is_active": new_user.is_active,
            "is_staff": new_user.is_staff,
            "is_superuser": new_user.is_superuser,
        }
    }

@router.get("/users", dependencies=[
        # Depends(login_required),
        # Depends(staff_required),
        # Depends(permission_required("view_user")),
    ]
)
async def get_all_users():
    return await User.all().values(
        "id", "username", "email", "is_active", "is_staff", "is_superuser", "created_at", "updated_at"
    )


@router.get(
    "/users/{user_id}",
    dependencies=[Depends(login_required)]
)
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    user = await User.get_or_none(id=user_id).prefetch_related("groups", "user_permissions")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # --- NORMAL USERS: can only access their own profile with limited data ---
    if not current_user.is_staff and not current_user.is_superuser:
        if current_user.id != user.id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this user."
            )
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at,
        }

    # --- STAFF/SUPERUSER: can view others with more detail ---
    groups = [group.name for group in await user.groups.all()]
    user_perms = [perm.codename for perm in await user.user_permissions.all()]

    # If superuser, also collect group perms
    group_perms = []
    if current_user.is_superuser:
        for group in await user.groups.all():
            perms = await group.permissions.all()
            group_perms.extend([perm.codename for perm in perms])

    all_perms = list(set(user_perms + group_perms))

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "groups": groups,
        "permissions": all_perms,
    }



@router.put(
    "/users/{user_id}",
    dependencies=[Depends(login_required)]  # user must be logged in
)
async def update_user(
    user_id: int,
    username: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_staff: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    group_ids: Optional[List[int]] = None,
    permission_ids: Optional[List[int]] = None,
    current_user: User = Depends(get_current_user),  # your auth dependency
):
    user = await User.get_or_none(id=user_id).prefetch_related("groups", "user_permissions")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # --- PERMISSION LOGIC ---
    if not current_user.is_superuser:
        if current_user.id != user.id:
            # staff can update other users, normal users cannot
            if not current_user.is_staff:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this user."
                )
        
        # normal users cannot touch sensitive fields
        if not current_user.is_staff:
            if any(v is not None for v in [is_active, is_staff, is_superuser, group_ids, permission_ids]):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not allowed to update these fields."
                )

        # staff users cannot update superuser flag
        if current_user.is_staff and not current_user.is_superuser:
            if is_superuser is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not allowed to change superuser status."
                )

    # --- UPDATE FIELDS ---
    if username:
        user.username = username
    if email:
        user.email = email
    if password:
        user.password = pwd_context.hash(password)
    if is_active is not None:
        user.is_active = is_active
    if is_staff is not None:
        user.is_staff = is_staff
    if is_superuser is not None:
        user.is_superuser = is_superuser

    await user.save()

    # Update groups
    if group_ids is not None:
        groups = await Group.filter(id__in=group_ids)
        await user.groups.clear()
        await user.groups.add(*groups)

    # Update permissions
    if permission_ids is not None:
        permissions = await Permission.filter(id__in=permission_ids)
        await user.user_permissions.clear()
        await user.user_permissions.add(*permissions)

    return {
        "detail": "User updated successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "groups": [g.id for g in await user.groups.all()],
            "permissions": [p.id for p in await user.user_permissions.all()],
        }
    }



@router.delete("/users/{user_id}", dependencies=[
        Depends(login_required),
        Depends(staff_required),
        Depends(permission_required("delete_user")),
    ]
)
async def delete_user(user_id: int):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await user.delete()
    return {"detail": "User deleted successfully"}

