# from fastapi import APIRouter
# from applications.items.models import ItemInstance


# router = APIRouter(prefix="/items", tags=["Item Intance"])

# @router('/')
# async def item():
#     item = await ItemInstance.all()
#     return item

# Fake permission dependency for example
# async def permission_required(action: str):
#     async def wrapper():
#         return True
#     return wrapper

# @router.post("/", dependencies=[Depends(permission_required("add_book"))])
# async def create_book(
#     title: str = Form(...),
#     category_id: int = Form(...),
#     subcategory_id: Optional[int] = Form(None),
#     book_type: Optional[str] = Form('academic_book'),
#     author: str = Form(...),
#     publisher: Optional[str] = Form(None),
#     isbn: Optional[str] = Form(None),
#     edition: Optional[str] = Form(None),
#     total_pages: Optional[int] = Form(None),
#     language: Optional[str] = Form(None),
#     publication_date: Optional[str] = Form(None),  # ISO format date string
#     description: Optional[str] = Form(None),
#     short_bio: Optional[str] = Form(None),
#     price: float = Form(0.0),
#     discount: float = Form(0.0),
#     box_price: float = Form(0.0),
#     stock: int = Form(0),
#     popular: bool = Form(False),
#     free_delivery: bool = Form(False),
#     hot_deals: bool = Form(False),
#     flash_sale: bool = Form(False),
#     image: Optional[UploadFile] = None,
#     file_sample: Optional[UploadFile] = None,
#     file_full: Optional[UploadFile] = None,
# ):
#     async with in_transaction():
#         pub_date = None
#         if publication_date:
#             try:
#                 pub_date = datetime.fromisoformat(publication_date)
#             except ValueError:
#                 raise HTTPException(status_code=400, detail="Invalid date format")

#         book = Book(
#             title=title,
#             category_id=category_id,
#             subcategory_id=subcategory_id,
#             book_type=book_type,
#             author=author,
#             publisher=publisher,
#             isbn=isbn,
#             edition=edition,
#             total_pages=total_pages,
#             language=language,
#             publication_date=pub_date,
#             description=description,
#             short_bio=short_bio,
#             price=price,
#             discount=discount,
#             box_price=box_price,
#             stock=stock,
#             popular=popular,
#             free_delivery=free_delivery,
#             hot_deals=hot_deals,
#             flash_sale=flash_sale,
#         )

#         # Handle file uploads (save path to model)
#         if image:
#             book.image = f"media/books/{image.filename}"
#             with open(f"media/books/{image.filename}", "wb") as f:
#                 f.write(await image.read())

#         if file_sample:
#             book.file_sample = f"media/books/{file_sample.filename}"
#             with open(f"media/books/{file_sample.filename}", "wb") as f:
#                 f.write(await file_sample.read())

#         if file_full:
#             book.file_full = f"media/books/{file_full.filename}"
#             with open(f"media/books/{file_full.filename}", "wb") as f:
#                 f.write(await file_full.read())

#         await book.save()
#         return {"success": True, "book_id": book.id, "title": book.title}







# Pydantic models
# Category_Pydantic = pydantic_model_creator(Category, name="Category")
# CategoryIn_Pydantic = pydantic_model_creator(Category, name="CategoryIn", exclude_readonly=True)

# Create Category
# @router.post("/", response_model=Category_Pydantic, dependencies=[Depends(permission_required("add_category"))])
# async def create_category(
#     name: str = Form(...),
#     description: Optional[str] = Form(None),
#     category_type: Optional[str] = Form("book"),
#     avatar: Optional[UploadFile] = File(None)
# ):
#     valid_types = ["book", "product", "course"]
#     if category_type not in valid_types:
#         raise HTTPException(status_code=400, detail="Invalid type")

#     if await Category.filter(name=name).exists():
#         raise HTTPException(status_code=400, detail="Category already exists")

#     avatar_path = None
#     if avatar and avatar.filename:
#         avatar_path = await save_file(avatar, upload_to="category_avatars")

#     category = await Category.create(
#         name=name,
#         description=description,
#         type=category_type,
#         avatar=avatar_path
#     )
#     return await Category_Pydantic.from_tortoise_orm(category)


# # List all Categories
# @router.get("/", response_model=List[Category_Pydantic])
# async def list_categories():
#     return await Category_Pydantic.from_queryset(Category.all())


# # Get single Category by ID
# @router.get("/{category_id}", response_model=Category_Pydantic)
# async def get_category(category_id: int):
#     category = await Category_Pydantic.from_queryset_single(Category.get(id=category_id))
#     return category


# # Update Category
# @router.put("/{category_id}", response_model=Category_Pydantic, dependencies=[Depends(permission_required("update_category"))])
# async def update_category(
#     category_id: int,
#     name: Optional[str] = Form(None),
#     description: Optional[str] = Form(None),
#     category_type: Optional[str] = Form(None),
#     avatar: Optional[UploadFile] = File(None)
# ):
#     category_obj = await Category.get_or_none(id=category_id)
#     if not category_obj:
#         raise HTTPException(status_code=404, detail="Category not found")

#     if name and name != category_obj.name:
#         if await Category.filter(name=name).exists():
#             raise HTTPException(status_code=400, detail="Name already exists")

#     update_data = {}

#     if name:
#         update_data["name"] = name
#     if description:
#         update_data["description"] = description
#     if category_type:
#         valid_types = ["book", "product", "course"]
#         if category_type not in valid_types:
#             raise HTTPException(status_code=400, detail="Invalid category type")
#         update_data["type"] = category_type

#     # File update
#     if avatar and avatar.filename:
#         avatar_path = await update_file(
#             avatar, category_obj.avatar, upload_to="category_avatars"
#         )
#         update_data["avatar"] = avatar_path

#     if update_data:
#         await Category.filter(id=category_id).update(**update_data)

#     return await Category_Pydantic.from_tortoise_orm(
#         await Category.get(id=category_id)
#     )


# # Delete Category
# @router.delete("/{category_id}", response_model=dict, dependencies=[Depends(permission_required("delete_category"))])
# async def delete_category(category_id: int):
#     category_obj = await Category.get_or_none(id=category_id)
#     if not category_obj:
#         raise HTTPException(status_code=404, detail="Category not found")

#     if category_obj.avatar:
#         await delete_file(category_obj.avatar)

#     await Category.filter(id=category_id).delete()
#     return {"detail": "Category deleted successfully"}





from fastapi import APIRouter
from tortoise.contrib.pydantic import pydantic_model_creator
from applications.items.models import ItemInstance  # assuming this exists

router = APIRouter(prefix="/items", tags=["Items"])

# Create Pydantic model
Item_Pydantic = pydantic_model_creator(ItemInstance, name="Item")

@router.get("/", response_model=list[Item_Pydantic])
async def get_items():
    items = await Item_Pydantic.from_queryset(ItemInstance.all())
    return items