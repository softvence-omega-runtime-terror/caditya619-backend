from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends, File
from tortoise.contrib.pydantic import pydantic_model_creator
from typing import List, Optional
from applications.items.models import SubCategory, Category
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required

router = APIRouter(prefix="/subcategories", tags=["SubCategories"])

# Pydantic models
SubCategory_Pydantic = pydantic_model_creator(SubCategory, name="SubCategory")
SubCategoryIn_Pydantic = pydantic_model_creator(SubCategory, name="SubCategoryIn", exclude_readonly=True)


# Create SubCategory
@router.post("/", response_model=SubCategory_Pydantic, dependencies=[Depends(permission_required("add_subcategory"))])
async def create_subcategory(
        category_id: int = Form(...),
        name: str = Form(...),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    # Validate category
    category_obj = await Category.get_or_none(id=category_id)
    if not category_obj:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if name already exists under this category
    if await SubCategory.filter(category_id=category_id, name=name).exists():
        raise HTTPException(status_code=400, detail="SubCategory already exists in this category")

    # Handle avatar upload
    avatar_path = None
    if avatar and avatar.filename:
        avatar_path = await save_file(
            avatar, upload_to="subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg']
        )

    # Create subcategory
    subcategory = await SubCategory.create(
        category=category_obj,
        name=name,
        description=description,
        avatar=avatar_path
    )
    return await SubCategory_Pydantic.from_tortoise_orm(subcategory)


# List all SubCategories
@router.get("/", response_model=List[SubCategory_Pydantic])
async def list_subcategories():
    return await SubCategory_Pydantic.from_queryset(SubCategory.all())


# Get single SubCategory
@router.get("/{subcategory_id}", response_model=SubCategory_Pydantic)
async def get_subcategory(subcategory_id: int):
    subcategory = await SubCategory_Pydantic.from_queryset_single(SubCategory.get(id=subcategory_id))
    return subcategory


# Update SubCategory
@router.put("/update", response_model=SubCategory_Pydantic,
            dependencies=[Depends(permission_required("update_subcategory"))])
async def update_subcategory(
        subcategory_id: int,
        category_id: Optional[int] = Form(None),
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    subcategory_obj = await SubCategory.get_or_none(id=subcategory_id)
    if not subcategory_obj:
        raise HTTPException(status_code=404, detail="SubCategory not found")

    update_data = {}

    # Handle category change
    if category_id is not None:
        category_obj = await Category.get_or_none(id=category_id)
        if not category_obj:
            raise HTTPException(status_code=404, detail="Category not found")
        update_data["category"] = category_obj

    # Handle name change and uniqueness
    if name and name != subcategory_obj.name:
        new_category_id = category_id if category_id else subcategory_obj.category.id
        if await SubCategory.filter(category_id=new_category_id, name=name).exclude(id=subcategory_id).exists():
            raise HTTPException(status_code=400, detail="SubCategory already exists in this category")
        update_data["name"] = name

    if description:
        update_data["description"] = description

    # Handle avatar update
    if avatar and avatar.filename:
        avatar_path = await update_file(
            avatar, subcategory_obj.avatar, upload_to="subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg']
        )
        update_data["avatar"] = avatar_path

    if update_data:
        await SubCategory.filter(id=subcategory_id).update(**update_data)

    return await SubCategory_Pydantic.from_tortoise_orm(
        await SubCategory.get(id=subcategory_id)
    )


# Delete SubCategory
@router.delete("/delete", response_model=dict,
               dependencies=[Depends(permission_required("delete_subcategory"))])
async def delete_subcategory(subcategory_id: int):
    subcategory_obj = await SubCategory.get_or_none(id=subcategory_id)
    if not subcategory_obj:
        raise HTTPException(status_code=404, detail="SubCategory not found")

    # Delete associated file if exists
    if subcategory_obj.avatar:
        await delete_file(subcategory_obj.avatar)

    await SubCategory.filter(id=subcategory_id).delete()
    return {"detail": "SubCategory deleted successfully"}
