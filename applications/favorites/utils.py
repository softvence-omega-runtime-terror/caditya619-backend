from applications.items.models import Item
from applications.favorites.schemas import (
    ItemDetail,
    CategoryBasic,
    SubCategoryBasic,
    SubSubCategoryBasic
)


async def serialize_item(item: Item) -> ItemDetail:
    """Serialize Item model to ItemDetail schema with all fields"""
    # Fetch related data
    await item.fetch_related("category", "subcategory", "sub_subcategory")
    
    # Serialize category
    category_data = CategoryBasic(
        id=item.category.id,
        name=item.category.name,
        type=item.category.type,
        avatar=item.category.avatar
    )
    
    # Serialize subcategory if exists
    subcategory_data = None
    if item.subcategory:
        subcategory_data = SubCategoryBasic(
            id=item.subcategory.id,
            name=item.subcategory.name,
            avatar=item.subcategory.avatar
        )
    
    # Serialize sub_subcategory if exists
    sub_subcategory_data = None
    if item.sub_subcategory:
        sub_subcategory_data = SubSubCategoryBasic(
            id=item.sub_subcategory.id,
            name=item.sub_subcategory.name,
            avatar=item.sub_subcategory.avatar
        )
    
    return ItemDetail(
        id=item.id,
        title=item.title,
        description=item.description,
        image=item.image,
        price=item.price,
        discount=item.discount,
        discounted_price=item.discounted_price,
        sell_price=item.sell_price,
        ratings=item.ratings,
        stock=item.stock,
        total_sale=item.total_sale,
        popular=item.popular,
        free_delivery=item.free_delivery,
        hot_deals=item.hot_deals,
        flash_sale=item.flash_sale,
        weight=item.weight,
        isOTC=item.isOTC,
        isSignature=item.isSignature,
        is_in_stock=item.is_in_stock,
        new_arrival=item.new_arrival,
        today_deals=item.today_deals,
        created_at=item.created_at,
        updated_at=item.updated_at,
        category=category_data,
        subcategory=subcategory_data,
        sub_subcategory=sub_subcategory_data
    )