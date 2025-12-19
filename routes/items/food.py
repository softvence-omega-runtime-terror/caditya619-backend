from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends
from tortoise.contrib.pydantic import pydantic_model_creator
from tortoise.transactions import in_transaction
from typing import Optional, List

from app.token import get_current_user
from applications.items.models import Item, Category, SubCategory, SubSubCategory
from app.utils.file_manager import save_file, update_file, delete_file
from app.auth import permission_required, vendor_required
import json

from applications.user.models import User
from routes.items import sub_subcategory

router = APIRouter(prefix="/food", tags=["Foods"])

ItemOut = pydantic_model_creator(Item, name="ItemOut")


# ----------------------- FORMATTER -----------------------
def format_float(value):
    return f"{float(value):.2f}" if value is not None else None


# ----------------------- SERIALIZE ITEM -----------------------
async def serialize_item(item: Item):
    await item.fetch_related("category", "subcategory", "sub_subcategory", "vendor__vendor_profile")

    vendor = item.vendor
    vendor_profile = vendor.vendor_profile if hasattr(vendor, "vendor_profile") else None

    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "category_id": item.category_id,
        "subcategory_id": item.subcategory_id,
        "sub_subcategory_id": item.sub_subcategory_id,
        "price": format_float(item.price),
        "discount": item.discount,
        "discounted_price": format_float(item.discounted_price),
        "sell_price": format_float(item.sell_price),
        "ratings": item.ratings,
        "total_reviews": await item.get_total_reviews(),
        "ratings_summery": await item.get_rating_summary_percentage(),
        "stock": item.stock,
        "total_sale": item.total_sale,
        "popular": item.popular,
        "free_delivery": item.free_delivery,
        "hot_deals": item.hot_deals,
        "flash_sale": item.flash_sale,
        "weight": item.weight,
        "vendor_id": vendor.id,
        "shop_image": vendor_profile.photo if vendor and vendor_profile else None,
        "shop_name": vendor.name,
        "image": item.image,
        "isSignature": item.isSignature,
        "is_in_stock": item.is_in_stock,
        "new_arrival": item.new_arrival,
        "today_deals": item.today_deals,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }



# ----------------------- CREATE -----------------------
@router.post("/", response_model=dict, dependencies=[Depends(vendor_required)])
async def create_item(
        title: str = Form(...),
        description: Optional[str] = Form(None),
        subcategory_id: Optional[int] = Form(None),
        sub_subcategory_id: Optional[int] = Form(None),
        price: float = Form(0.0),
        discount: int = Form(0),
        stock: int = Form(0),
        popular: bool = Form(False),
        free_delivery: bool = Form(False),
        hot_deals: bool = Form(False),
        flash_sale: bool = Form(False),
        weight: Optional[float] = Form(None),
        image: Optional[UploadFile] = None,
        isSignature: bool = Form(False),
        vendor: User = Depends(get_current_user)
):
    async with in_transaction() as conn:
        vendor_profile = await vendor.vendor_profile
        category = await Category.filter(type='food').first()
        if vendor_profile.type != 'food':
            raise HTTPException(status_code=403, detail="Vendor type mismatch")

        subcategory = await SubCategory.get_or_none(id=subcategory_id, using_db=conn) if subcategory_id else None
        sub_subcategory = await SubSubCategory.get_or_none(
            id=sub_subcategory_id, using_db=conn
        ) if sub_subcategory_id else None

        img_path = None
        if image:
            img_path = await save_file(image, "item_images")

        item = await Item.create(
            title=title,
            description=description,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            price=price,
            discount=discount,
            stock=stock,
            popular=popular,
            free_delivery=free_delivery,
            hot_deals=hot_deals,
            flash_sale=flash_sale,
            weight=weight,
            vendor=vendor,
            image=img_path,
            isSignature=isSignature,
            using_db=conn,
        )

    data = await serialize_item(item)
    return {"status": "success", "data": data}


# ----------------------- GET ALL -----------------------
# @router.get("/", response_model=dict)
# async def get_all_items():
#     items = await Item.all().prefetch_related("category", "subcategory", "sub_subcategory")
#     data = [await serialize_item(item) for item in items]
#     return {"status": "success", "count": len(data), "data": data}


@router.get("/my-product", response_model=dict)
async def get_all_items(
    category: Optional[int] = None,
    subcategory: Optional[int] = None,
    vendor_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    new_arrival: Optional[bool] = None,
    today_deals: Optional[bool] = None,
    popular: Optional[bool] = None,
    free_delivery: Optional[bool] = None,
    hot_deals: Optional[bool] = None,
    flash_sale: Optional[bool] = None,
    isSignature: Optional[bool] = None,
    name: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
    vendor: User = Depends(vendor_required),
):
    query = Item.filter(category__type='food', vendor=vendor).prefetch_related("category", "subcategory", "sub_subcategory")

    if category:
        query = query.filter(category_id=category)
    if subcategory:
        query = query.filter(subcategory_id=subcategory)
    if vendor_id:
        query = query.filter(vendor_id=vendor_id)
    if min_price is not None:
        query = query.filter(price__gte=min_price)
    if max_price is not None:
        query = query.filter(price__lte=max_price)
    if new_arrival is not None:
        query = query.filter(new_arrival=new_arrival)
    if today_deals is not None:
        query = query.filter(today_deals=today_deals)
    if popular is not None:
        query = query.filter(popular=popular)
    if free_delivery is not None:
        query = query.filter(free_delivery=free_delivery)
    if hot_deals is not None:
        query = query.filter(hot_deals=hot_deals)
    if flash_sale is not None:
        query = query.filter(flash_sale=flash_sale)
    if isSignature is not None:
        query = query.filter(isSignature=isSignature)
    if name:
        query = query.filter(name__icontains=name)

    total_count = await query.count()
    low_stock_count = await query.filter(stock__lt=10).count()
    items = await query.offset(offset).limit(limit)
    data = [await serialize_item(item) for item in items]

    return {
        "status": "success",
        "count": len(data),
        "low_stock_count": low_stock_count,
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "data": data
    }




@router.get("/", response_model=dict)
async def get_all_items(
    category: Optional[int] = None,
    subcategory: Optional[int] = None,
    vendor_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    new_arrival: Optional[bool] = None,
    today_deals: Optional[bool] = None,
    popular: Optional[bool] = None,
    free_delivery: Optional[bool] = None,
    hot_deals: Optional[bool] = None,
    flash_sale: Optional[bool] = None,
    isSignature: Optional[bool] = None,
    name: Optional[str] = None,
    offset: int = 0,
    limit: int = 20
):
    query = Item.filter(category__type='food').prefetch_related("category", "subcategory", "sub_subcategory")

    if category:
        query = query.filter(category_id=category)
    if subcategory:
        query = query.filter(subcategory_id=subcategory)
    if vendor_id:
        query = query.filter(vendor_id=vendor_id)
    if min_price is not None:
        query = query.filter(price__gte=min_price)
    if max_price is not None:
        query = query.filter(price__lte=max_price)
    if new_arrival is not None:
        query = query.filter(new_arrival=new_arrival)
    if today_deals is not None:
        query = query.filter(today_deals=today_deals)
    if popular is not None:
        query = query.filter(popular=popular)
    if free_delivery is not None:
        query = query.filter(free_delivery=free_delivery)
    if hot_deals is not None:
        query = query.filter(hot_deals=hot_deals)
    if flash_sale is not None:
        query = query.filter(flash_sale=flash_sale)
    if isSignature is not None:
        query = query.filter(isSignature=isSignature)
    if name:
        query = query.filter(name__icontains=name)

    total_count = await query.count()
    items = await query.offset(offset).limit(limit)
    data = [await serialize_item(item) for item in items]

    return {
        "status": "success",
        "count": len(data),
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "data": data
    }


# ----------------------- GET SINGLE -----------------------
@router.get("/{item_id}", response_model=dict)
async def get_item(item_id: int):
    item = await Item.get_or_none(id=item_id).prefetch_related("category", "subcategory", "sub_subcategory")
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    data = await serialize_item(item)
    return {"status": "success", "data": data}


# ----------------------- UPDATE -----------------------
@router.put("/{item_id}", response_model=dict)
async def update_item(
        item_id: int,
        title: str = Form(...),
        description: Optional[str] = Form(None),
        category_id: int = Form(...),
        subcategory_id: Optional[int] = Form(None),
        price: float = Form(0.0),
        discount: int = Form(0),
        stock: int = Form(0),
        is_stock: bool = Form(False),
        popular: bool = Form(False),
        free_delivery: bool = Form(False),
        hot_deals: bool = Form(False),
        flash_sale: bool = Form(False),
        weight: Optional[float] = Form(None),
        image: Optional[UploadFile] = None,
        isSignature: bool = Form(False),
        vendor: User = Depends(vendor_required),
):
    item = await Item.get_or_none(id=item_id, vendor=vendor)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    async with in_transaction() as conn:
        category = await Category.get_or_none(id=category_id, using_db=conn)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        subcategory = await SubCategory.get_or_none(id=subcategory_id, using_db=conn) if subcategory_id else None

        img_path = item.image
        if image:
            img_path = await update_file(image, item.image, "item_images")

        item.title = title
        item.description = description
        item.category = category
        item.subcategory = subcategory
        item.price = price
        item.discount = discount
        item.stock = stock
        item.is_stock = is_stock
        item.popular = popular
        item.free_delivery = free_delivery
        item.hot_deals = hot_deals
        item.flash_sale = flash_sale
        item.weight = weight
        item.image = img_path,
        item.isSignature = isSignature

        await item.save(using_db=conn)

    data = await serialize_item(item)
    return {"status": "success", "data": data}


# ----------------------- PARTIAL UPDATE -----------------------
@router.patch("/{item_id}", response_model=dict)
async def patch_item(
        item_id: int,
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        subcategory_id: Optional[int] = Form(None),
        price: Optional[float] = Form(None),
        discount: Optional[int] = Form(None),
        stock: Optional[int] = Form(None),
        is_stock: bool = Form(False),
        popular: Optional[bool] = Form(None),
        free_delivery: Optional[bool] = Form(None),
        hot_deals: Optional[bool] = Form(None),
        flash_sale: Optional[bool] = Form(None),
        weight: Optional[float] = Form(None),
        image: Optional[UploadFile] = None,
        isSignature: bool = Form(False),
        vendor: User = Depends(vendor_required),
):
    item = await Item.get_or_none(id=item_id, vendor=vendor)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    async with in_transaction() as conn:
        if subcategory_id:
            subcategory = await SubCategory.get_or_none(id=subcategory_id, using_db=conn)
            if not subcategory:
                raise HTTPException(status_code=404, detail="SubCategory not found")
            item.subcategory = subcategory

        if image:
            item.image = await update_file(image, item.image, "item_images")

        # Dynamically update fields
        updates = {
            "title": title, "description": description, "price": price, "discount": discount,
            "stock": stock, "is_stock" : is_stock, "popular": popular, "free_delivery": free_delivery,
            "hot_deals": hot_deals, "flash_sale": flash_sale,
            "weight": weight, "isSignature": isSignature
        }
        for k, v in updates.items():
            if v is not None:
                setattr(item, k, v)

        await item.save(using_db=conn)

    data = await serialize_item(item)
    return {"status": "success", "data": data}


# ----------------------- DELETE -----------------------
@router.delete("/{item_id}", response_model=dict)
async def delete_item(item_id: int, vendor: User = Depends(vendor_required),):
    item = await Item.get_or_none(id=item_id, vendor=vendor)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    async with in_transaction() as conn:
        if item.image:
            await delete_file(item.image)
        await item.delete(using_db=conn)

    return {"status": "success", "message": "Item deleted successfully"}
