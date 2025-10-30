from fastapi import APIRouter
from tortoise.contrib.pydantic import pydantic_model_creator
from applications.items.models import Item  # assuming this exists

router = APIRouter(prefix="/items", tags=["Items"])

# Create Pydantic model
Item_Pydantic = pydantic_model_creator(Item, name="Item")

@router.get("/", response_model=list[Item_Pydantic])
async def get_items():
    items = await Item_Pydantic.from_queryset(Item.all())
    return items