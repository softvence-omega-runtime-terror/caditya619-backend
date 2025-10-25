from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends, File
from tortoise.contrib.pydantic import pydantic_model_creator
from typing import List, Optional
from applications.items.models import SubSubCategory, SubCategory
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required

router = APIRouter(prefix="/sub-subcategories", tags=["Sub-SubCategories"])

# Pydantic models
SubSubCategory_Pydantic = pydantic_model_creator(SubSubCategory, name="SubSubCategory")
SubSubCategoryIn_Pydantic = pydantic_model_creator(SubSubCategory, name="SubSubCategoryIn", exclude_readonly=True)


# Create SubSubCategory
@router.post("/", response_model=SubSubCategory_Pydantic,
             dependencies=[Depends(permission_required("add_subsubcategory"))])
async def create_sub_subcategory(
        subcategory_id: int = Form(...),
        name: str = Form(...),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    # Validate SubCategory
    subcategory_obj = await SubCategory.get_or_none(id=subcategory_id)
    if not subcategory_obj:
        raise HTTPException(status_code=404, detail="SubCategory not found")

    # Check if name already exists under this SubCategory
    if await SubSubCategory.filter(subcategory_id=subcategory_id, name=name).exists():
        raise HTTPException(status_code=400, detail="SubSubCategory already exists in this SubCategory")

    # Handle avatar upload
    avatar_path = None
    if avatar and avatar.filename:
        avatar_path = await save_file(
            avatar, upload_to="sub_subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg']
        )

    # Create SubSubCategory
    sub_subcategory = await SubSubCategory.create(
        subcategory=subcategory_obj,
        name=name,
        description=description,
        avatar=avatar_path
    )

    return await SubSubCategory_Pydantic.from_tortoise_orm(sub_subcategory)


# List all SubSubCategories
@router.get("/", response_model=List[SubSubCategory_Pydantic])
async def list_sub_subcategories(subcategory_id: Optional[int] = None):
    """List all SubSubCategories or filter by subcategory_id"""
    if subcategory_id:
        return await SubSubCategory_Pydantic.from_queryset(
            SubSubCategory.filter(subcategory_id=subcategory_id)
        )
    return await SubSubCategory_Pydantic.from_queryset(SubSubCategory.all())


# Get single SubSubCategory
@router.get("/{sub_subcategory_id}", response_model=SubSubCategory_Pydantic)
async def get_sub_subcategory(sub_subcategory_id: int):
    sub_subcategory = await SubSubCategory_Pydantic.from_queryset_single(
        SubSubCategory.get(id=sub_subcategory_id)
    )
    return sub_subcategory


# Update SubSubCategory
@router.put("/update", response_model=SubSubCategory_Pydantic,
            dependencies=[Depends(permission_required("update_subsubcategory"))])
async def update_sub_subcategory(
        sub_subcategory_id: int,
        subcategory_id: Optional[int] = Form(None),
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    sub_subcategory_obj = await SubSubCategory.get_or_none(id=sub_subcategory_id)
    if not sub_subcategory_obj:
        raise HTTPException(status_code=404, detail="Sub SubCategory not found")

    update_data = {}

    # Handle SubCategory change
    if subcategory_id is not None:
        subcategory_obj = await SubCategory.get_or_none(id=subcategory_id)
        if not subcategory_obj:
            raise HTTPException(status_code=404, detail="SubCategory not found")
        update_data["subcategory"] = subcategory_obj

    # Handle name change and uniqueness
    if name and name != sub_subcategory_obj.name:
        new_subcategory_id = subcategory_id if subcategory_id else sub_subcategory_obj.subcategory.id
        if await SubSubCategory.filter(subcategory_id=new_subcategory_id, name=name).exclude(
                id=sub_subcategory_id).exists():
            raise HTTPException(status_code=400, detail="SubSubCategory already exists in this SubCategory")
        update_data["name"] = name

    # Handle description
    if description:
        update_data["description"] = description

    # Handle avatar update
    if avatar and avatar.filename:
        avatar_path = await update_file(
            avatar, sub_subcategory_obj.avatar, upload_to="sub_subcategory_avatars",
            allowed_extensions=['png', 'jpg', 'svg']
        )
        update_data["avatar"] = avatar_path

    # Apply updates
    if update_data:
        await SubSubCategory.filter(id=sub_subcategory_id).update(**update_data)

    return await SubSubCategory_Pydantic.from_tortoise_orm(
        await SubSubCategory.get(id=sub_subcategory_id)
    )


# Delete SubSubCategory
@router.delete("/delete", response_model=dict, dependencies=[Depends(permission_required("delete_subsubcategory"))])
async def delete_sub_subcategory(sub_subcategory_id: int):
    sub_subcategory_obj = await SubSubCategory.get_or_none(id=sub_subcategory_id)
    if not sub_subcategory_obj:
        raise HTTPException(status_code=404, detail="Sub SubCategory not found")

    # Delete associated avatar file if exists
    if sub_subcategory_obj.avatar:
        await delete_file(sub_subcategory_obj.avatar)

    await SubSubCategory.filter(id=sub_subcategory_id).delete()
    return {"detail": "Sub SubCategory deleted successfully"}
