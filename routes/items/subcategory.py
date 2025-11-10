from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends, File
from tortoise.transactions import in_transaction
from typing import Optional, List
from applications.items.models import SubCategory, Category
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required

router = APIRouter(prefix="/subcategories", tags=["SubCategories"])


# ----------------------- FORMATTER -----------------------
def format_datetime(dt):
    return dt.isoformat() if dt else None


# ----------------------- SERIALIZE SUBCATEGORY -----------------------
async def serialize_subcategory(sub: SubCategory):
    await sub.fetch_related("category")
    return {
        "id": sub.id,
        "name": sub.name,
        "description": getattr(sub, "description", None),
        "avatar": sub.avatar,
        "created_at": format_datetime(sub.created_at),
        "category": {
            "id": sub.category.id,
            "name": sub.category.name
        } if sub.category else None
    }


# ----------------------- CREATE -----------------------
@router.post("/", response_model=dict, dependencies=[Depends(permission_required("add_subcategory"))])
async def create_subcategory(
        category_id: int = Form(...),
        name: str = Form(...),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    async with in_transaction() as conn:
        category = await Category.get_or_none(id=category_id, using_db=conn)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        if await SubCategory.filter(category_id=category_id, name=name).using_db(conn).exists():
            raise HTTPException(status_code=400, detail="SubCategory already exists in this category")

        avatar_path = None
        if avatar and avatar.filename:
            avatar_path = await save_file(avatar, upload_to="subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg'])

        subcategory = await SubCategory.create(
            category=category,
            name=name,
            description=description,
            avatar=avatar_path,
            using_db=conn
        )

    data = await serialize_subcategory(subcategory)
    return {"status": "success", "data": data}


# ----------------------- LIST ALL -----------------------
@router.get("/", response_model=dict)
async def list_subcategories(category_id: Optional[int] = None):
    query = SubCategory.all().prefetch_related("category")
    if category_id:
        query = query.filter(category_id=category_id)

    items = [await serialize_subcategory(sub) for sub in await query]
    return {"status": "success", "count": len(items), "data": items}


# ----------------------- GET SINGLE -----------------------
@router.get("/{subcategory_id}", response_model=dict)
async def get_subcategory(subcategory_id: int):
    sub = await SubCategory.get_or_none(id=subcategory_id).prefetch_related("category")
    if not sub:
        raise HTTPException(status_code=404, detail="SubCategory not found")
    data = await serialize_subcategory(sub)
    return {"status": "success", "data": data}


# ----------------------- UPDATE -----------------------
@router.put("/update", response_model=dict, dependencies=[Depends(permission_required("update_subcategory"))])
async def update_subcategory(
        subcategory_id: int = Form(...),
        category_id: Optional[int] = Form(None),
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    sub = await SubCategory.get_or_none(id=subcategory_id)
    if not sub:
        raise HTTPException(status_code=404, detail="SubCategory not found")

    update_data = {}

    if category_id is not None:
        category = await Category.get_or_none(id=category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        update_data["category"] = category

    if name and name != sub.name:
        new_cat_id = category_id if category_id else sub.category.id
        if await SubCategory.filter(category_id=new_cat_id, name=name).exclude(id=subcategory_id).exists():
            raise HTTPException(status_code=400, detail="SubCategory already exists in this category")
        update_data["name"] = name

    if description is not None:
        update_data["description"] = description

    if avatar and avatar.filename:
        avatar_path = await update_file(avatar, sub.avatar, upload_to="subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg'])
        update_data["avatar"] = avatar_path

    if update_data:
        await SubCategory.filter(id=subcategory_id).update(**update_data)

    updated_sub = await SubCategory.get(id=subcategory_id).prefetch_related("category")
    data = await serialize_subcategory(updated_sub)
    return {"status": "success", "data": data}


# ----------------------- DELETE -----------------------
@router.delete("/delete", response_model=dict, dependencies=[Depends(permission_required("delete_subcategory"))])
async def delete_subcategory(subcategory_id: int):
    sub = await SubCategory.get_or_none(id=subcategory_id)
    if not sub:
        raise HTTPException(status_code=404, detail="SubCategory not found")

    if sub.avatar:
        await delete_file(sub.avatar)

    await SubCategory.filter(id=subcategory_id).delete()
    return {"status": "success", "detail": "SubCategory deleted successfully"}
