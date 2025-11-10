from tortoise.exceptions import IntegrityError
from applications.items.models import Category

CATEGORIES_DATA = [
    {"name": "Food", "type": "food", "avatar": "https://via.placeholder.com/300x300?text=Food"},
    {"name": "Groceries", "type": "groceries", "avatar": "https://via.placeholder.com/300x300?text=Groceries"},
    {"name": "Cleaning", "type": "groceries", "avatar": "https://via.placeholder.com/300x300?text=Cleaning"},
    {"name": "Personal Care", "type": "groceries", "avatar": "https://via.placeholder.com/300x300?text=Personal+Care"},
    {"name": "Pet Supplies", "type": "groceries", "avatar": "https://via.placeholder.com/300x300?text=Pet+Supplies"},
    {"name": "Medicine", "type": "medicine", "avatar": "https://via.placeholder.com/300x300?text=Medicine"},
]


async def create_test_categories():
    for data in CATEGORIES_DATA:
        name = data["name"]

        existing = await Category.filter(name=name).first()
        if existing:
            continue

        try:
            category = await Category.create(**data)
            print(f"Created category: {category.name} ({category.type})")

        except IntegrityError as e:
            print(f"IntegrityError for '{name}': {e}")
        except Exception as e:
            print(f"Unexpected error for '{name}': {e}")

    print("\nAll test categories created successfully!\n")
