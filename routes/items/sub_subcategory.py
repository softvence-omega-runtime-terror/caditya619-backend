from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends, File
from tortoise.transactions import in_transaction
from typing import Optional, List
from applications.items.models import SubSubCategory, SubCategory
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required

router = APIRouter(prefix="/sub-subcategories", tags=["Sub-SubCategories"])


# ----------------------- FORMATTER -----------------------
def format_datetime(dt):
    return dt.isoformat() if dt else None


# ----------------------- SERIALIZE SUBSUBCATEGORY -----------------------
async def serialize_sub_subcategory(sub_sub: SubSubCategory):
    await sub_sub.fetch_related("subcategory", "subcategory__category")
    return {
        "id": sub_sub.id,
        "name": sub_sub.name,
        "description": getattr(sub_sub, "description", None),
        "avatar": sub_sub.avatar,
        "created_at": format_datetime(sub_sub.created_at),
        "subcategory": {
            "id": sub_sub.subcategory.id,
            "name": sub_sub.subcategory.name,
            "category": {
                "id": sub_sub.subcategory.category.id,
                "name": sub_sub.subcategory.category.name
            } if sub_sub.subcategory.category else None
        } if sub_sub.subcategory else None
    }


# ----------------------- CREATE -----------------------
@router.post("/", response_model=dict, dependencies=[Depends(permission_required("add_subsubcategory"))])
async def create_sub_subcategory(
        subcategory_id: int = Form(...),
        name: str = Form(...),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    async with in_transaction() as conn:
        subcategory = await SubCategory.get_or_none(id=subcategory_id, using_db=conn)
        if not subcategory:
            raise HTTPException(status_code=404, detail="SubCategory not found")

        if await SubSubCategory.filter(subcategory_id=subcategory_id, name=name).using_db(conn).exists():
            raise HTTPException(status_code=400, detail="SubSubCategory already exists in this SubCategory")

        avatar_path = None
        if avatar and avatar.filename:
            avatar_path = await save_file(
                avatar, upload_to="sub_subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg']
            )

        sub_subcategory = await SubSubCategory.create(
            subcategory=subcategory,
            name=name,
            description=description,
            avatar=avatar_path,
            using_db=conn
        )

    data = await serialize_sub_subcategory(sub_subcategory)
    return {"status": "success", "data": data}


# ----------------------- LIST ALL -----------------------
@router.get("/", response_model=dict)
async def list_sub_subcategories(subcategory_id: Optional[int] = None):
    query = SubSubCategory.all().prefetch_related("subcategory", "subcategory__category")
    if subcategory_id:
        query = query.filter(subcategory_id=subcategory_id)

    items = [await serialize_sub_subcategory(sub) for sub in await query]
    return {"status": "success", "count": len(items), "data": items}


# ----------------------- GET SINGLE -----------------------
@router.get("/{sub_subcategory_id}", response_model=dict)
async def get_sub_subcategory(sub_subcategory_id: int):
    sub = await SubSubCategory.get_or_none(id=sub_subcategory_id).prefetch_related("subcategory", "subcategory__category")
    if not sub:
        raise HTTPException(status_code=404, detail="SubSubCategory not found")
    data = await serialize_sub_subcategory(sub)
    return {"status": "success", "data": data}


# ----------------------- UPDATE -----------------------
@router.put("/update", response_model=dict, dependencies=[Depends(permission_required("update_subsubcategory"))])
async def update_sub_subcategory(
        sub_subcategory_id: int = Form(...),
        subcategory_id: Optional[int] = Form(None),
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        avatar: Optional[UploadFile] = File(None)
):
    sub_sub = await SubSubCategory.get_or_none(id=sub_subcategory_id)
    if not sub_sub:
        raise HTTPException(status_code=404, detail="SubSubCategory not found")

    update_data = {}

    if subcategory_id is not None:
        subcategory = await SubCategory.get_or_none(id=subcategory_id)
        if not subcategory:
            raise HTTPException(status_code=404, detail="SubCategory not found")
        update_data["subcategory"] = subcategory

    if name and name != sub_sub.name:
        new_subcategory_id = subcategory_id if subcategory_id else sub_sub.subcategory.id
        if await SubSubCategory.filter(subcategory_id=new_subcategory_id, name=name).exclude(id=sub_subcategory_id).exists():
            raise HTTPException(status_code=400, detail="SubSubCategory already exists in this SubCategory")
        update_data["name"] = name

    if description is not None:
        update_data["description"] = description

    if avatar and avatar.filename:
        avatar_path = await update_file(avatar, sub_sub.avatar, upload_to="sub_subcategory_avatars", allowed_extensions=['png', 'jpg', 'svg'])
        update_data["avatar"] = avatar_path

    if update_data:
        await SubSubCategory.filter(id=sub_subcategory_id).update(**update_data)

    updated_sub = await SubSubCategory.get(id=sub_subcategory_id).prefetch_related("subcategory", "subcategory__category")
    data = await serialize_sub_subcategory(updated_sub)
    return {"status": "success", "data": data}


# ----------------------- DELETE -----------------------
@router.delete("/delete", response_model=dict, dependencies=[Depends(permission_required("delete_subsubcategory"))])
async def delete_sub_subcategory(sub_subcategory_id: int):
    sub_sub = await SubSubCategory.get_or_none(id=sub_subcategory_id)
    if not sub_sub:
        raise HTTPException(status_code=404, detail="SubSubCategory not found")

    if sub_sub.avatar:
        await delete_file(sub_sub.avatar)

    await SubSubCategory.filter(id=sub_subcategory_id).delete()
    return {"status": "success", "detail": "SubSubCategory deleted successfully"}
