from tortoise.exceptions import IntegrityError
from applications.items.models import Category
#     {"id": 1, "name": "Food", "type": "food", "avatar": "https://i.ibb.co.com/XxHxgcQ3/Group-2.png"},
#     {"id": 2, "name": "Groceries", "type": "groceries", "avatar": "https://i.ibb.co.com/xKSX27Nf/Group-3.png"},
#     {"id": 3, "name": "Cleaning", "type": "groceries", "avatar": "https://i.ibb.co.com/HTL653Wt/Group-4.png"},
#     {"id": 4, "name": "Personal Care", "type": "groceries", "avatar": "https://i.ibb.co.com/nMLGrVk5/Group-5.png"},
#     {"id": 5, "name": "Pet Supplies", "type": "groceries", "avatar": "https://i.ibb.co.com/WWTmLyhz/Group-6.png"},
#     {"id": 6, "name": "Medicine", "type": "medicine", "avatar": "https://i.ibb.co.com/4ZN07fgy/Group-7.png"},


CATEGORIES_DATA = [
    {"id": 1, "name": "Food", "type": "food", "avatar": "https://i.ibb.co.com/XxHxgcQ3/Group-2.png"},
    {"id": 2, "name": "Groceries", "type": "groceries", "avatar": "https://i.ibb.co.com/xKSX27Nf/Group-3.png"},
    {"id": 3, "name": "Cleaning", "type": "groceries", "avatar": "https://i.ibb.co.com/HTL653Wt/Group-4.png"},
    {"id": 4, "name": "Personal Care", "type": "groceries", "avatar": "https://i.ibb.co.com/nMLGrVk5/Group-5.png"},
    {"id": 5, "name": "Pet Supplies", "type": "groceries", "avatar": "https://i.ibb.co.com/WWTmLyhz/Group-6.png"},
    {"id": 6, "name": "Medicine", "type": "medicine", "avatar": "https://i.ibb.co.com/4ZN07fgy/Group-7.png"},
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
