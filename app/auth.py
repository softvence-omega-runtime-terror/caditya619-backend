from fastapi import Depends, HTTPException, status
from typing import Optional
from .token import get_current_user
from applications.user.models import User

async def superuser_required(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


async def staff_required(current_user: User = Depends(get_current_user)):
    if not (current_user.is_staff or current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Staff access required")
    return current_user


async def rider_required(current_user: User = Depends(get_current_user)):
    if not (current_user.is_rider or current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Rider access required")
    return current_user


async def vendor_required(current_user: User = Depends(get_current_user)):
    if not (current_user.is_vendor or current_user.is_superuser):
        raise HTTPException(status_code=403, detail="vendor access required")
    return current_user

#
# def rider_required(codename: Optional[str] = None):
#     if callable(codename) and not isinstance(codename, str):
#         async def wrapper(current_user: User = Depends(get_current_user)):
#             if not (current_user.is_rider or current_user.is_superuser):
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail="Rider access required"
#                 )
#             return current_user
#         return wrapper
#     async def wrapper(current_user: User = Depends(get_current_user)):
#         if not (current_user.is_rider or current_user.is_superuser):
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Rider access required"
#             )
#         if codename:
#             has_perm = await current_user.has_permission(codename)
#             if not has_perm:
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail=f"Permission '{codename}' required"
#                 )
#         return current_user
#     return wrapper
#
#
#
# def vendor_required(codename: Optional[str] = None):
#     if callable(codename) and not isinstance(codename, str):
#         async def wrapper(current_user: User = Depends(get_current_user)):
#             if not (current_user.is_vendor or current_user.is_superuser):
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail="Vendor access required",
#                 )
#             return current_user
#         return wrapper
#     async def wrapper(current_user: User = Depends(get_current_user)):
#         if not (current_user.is_vendor or current_user.is_superuser):
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Vendor access required",
#             )
#         if codename:
#             has_perm = await current_user.has_permission(codename)
#             if not has_perm:
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail=f"Permission '{codename}' required",
#                 )
#         return current_user
#     return wrapper
#

async def login_required(current_user: User = Depends(get_current_user)):
    return current_user


def permission_required(codename: str):
    async def wrapper(current_user: User = Depends(get_current_user)):
        if not await current_user.has_permission(codename):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{codename}' required",
            )
        return current_user
    return wrapper