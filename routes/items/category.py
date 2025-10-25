from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends, File
from tortoise.contrib.pydantic import pydantic_model_creator
from typing import List, Optional
from applications.items.models import Category
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required

router = APIRouter(prefix="/categories", tags=["Categories"])

# Pydantic models
Category_Pydantic = pydantic_model_creator(Category, name="Category")
CategoryIn_Pydantic = pydantic_model_creator(Category, name="CategoryIn", exclude_readonly=True)

VALID_TYPES = ["book", "product", "course"]


# Create Category
@router.post("/", response_model=Category_Pydantic, dependencies=[Depends(permission_required("add_category"))])
async def create_category(
        name: str = Form(...),
        description: Optional[str] = Form(None),
        category_type: Optional[str] = Form("book"),
        avatar: Optional[UploadFile] = File(None)
):
    if category_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="Invalid type")

    if await Category.filter(name=name).exists():
        raise HTTPException(status_code=400, detail="Category already exists")

    avatar_path = None
    if avatar and avatar.filename:
        avatar_path = await save_file(avatar, upload_to="category_avatars", allowed_extensions=['png', 'jpg', 'svg'])

    category = await Category.create(
        name=name,
        description=description,
        type=category_type,
        avatar=avatar_path
    )
    return await Category_Pydantic.from_tortoise_orm(category)


# List all Categories
@router.get("/", response_model=List[Category_Pydantic])
async def list_categories():
    return await Category_Pydantic.from_queryset(Category.all())


# Get single Category by ID
@router.get("/{category_id}", response_model=Category_Pydantic)
async def get_category(category_id: int):
    category = await Category_Pydantic.from_queryset_single(Category.get(id=category_id))
    return category


# Update Category
@router.put("/update", response_model=Category_Pydantic,
            dependencies=[Depends(permission_required("update_category"))])
async def update_category(
        category_id: int,
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        category_type: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    category_obj = await Category.get_or_none(id=category_id)
    if not category_obj:
        raise HTTPException(status_code=404, detail="Category not found")

    if name and name != category_obj.name:
        if await Category.filter(name=name).exists():
            raise HTTPException(status_code=400, detail="Name already exists")

    update_data = {}
    if name:
        update_data["name"] = name
    if description:
        update_data["description"] = description
    if category_type:
        if category_type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail="Invalid category type")
        update_data["type"] = category_type

    # File update
    if avatar and avatar.filename:
        avatar_path = await update_file(
            avatar, category_obj.avatar, upload_to="category_avatars", allowed_extensions=['png', 'jpg', 'svg']
        )
        update_data["avatar"] = avatar_path

    if update_data:
        await Category.filter(id=category_id).update(**update_data)

    return await Category_Pydantic.from_tortoise_orm(
        await Category.get(id=category_id)
    )


# Delete Category
@router.delete("/delete", response_model=dict, dependencies=[Depends(permission_required("delete_category"))])
async def delete_category(category_id: int):
    category_obj = await Category.get_or_none(id=category_id)
    if not category_obj:
        raise HTTPException(status_code=404, detail="Category not found")

    if category_obj.avatar:
        await delete_file(category_obj.avatar)

    await Category.filter(id=category_id).delete()
    return {"detail": "Category deleted successfully"}
