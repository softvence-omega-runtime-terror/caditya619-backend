import random
from datetime import datetime, timedelta, timezone
from tortoise.exceptions import IntegrityError
from applications.items.models import Category, SubCategory, SubSubCategory, Item
from applications.user.models import User
from app.dummy.sub_categories import SUBCATEGORIES_DATA
from faker import Faker

fake = Faker()


async def create_dummy_items():
    vendors = await User.filter(is_vendor=True).all()
    if not vendors:
        print('No Vendor exist')
        return

    for category_name, subcategories in SUBCATEGORIES_DATA.items():
        try:
            category = await Category.get(name=category_name)
        except Category.DoesNotExist:
            print(f"Category '{category_name}' does not exist, skipping...")
            continue

        for subcat_data in subcategories:
            subcategory_name = subcat_data["name"]
            try:
                subcategory = await SubCategory.get(name=subcategory_name, category=category)
            except SubCategory.DoesNotExist:
                print(f"SubCategory '{subcategory_name}' does not exist, skipping...")
                continue

            for sub_subcat_data in subcat_data.get("sub_subcategories", []):
                sub_subcategory_name = sub_subcat_data["name"]
                try:
                    sub_subcategory = await SubSubCategory.get(
                        name=sub_subcategory_name, subcategory=subcategory
                    )
                except SubSubCategory.DoesNotExist:
                    print(f"SubSubCategory '{sub_subcategory_name}' does not exist, skipping...")
                    continue

                # 3. Create 10 items per sub-subcategory
                for i in range(10):
                    title = f"{sub_subcategory.name} Item {i+1}"
                    description = fake.text(max_nb_chars=200)
                    price = round(random.uniform(5, 100), 2)
                    discount = random.randint(0, 5)
                    stock = random.randint(0, 50)
                    weight = round(random.uniform(0.1, 5.0), 2)
                    ratings = round(random.uniform(0, 5), 1)
                    popular = random.choice([True, False])
                    free_delivery = random.choice([True, False])
                    hot_deals = random.choice([True, False])
                    flash_sale = random.choice([True, False])
                    isOTC = random.choice([True, False])
                    image = sub_subcat_data.get("avatar", None)
                    vendor = random.choice(vendors)

                    try:
                        await Item.create(
                            category=category,
                            subcategory=subcategory,
                            sub_subcategory=sub_subcategory,
                            title=title,
                            description=description,
                            price=price,
                            discount=discount,
                            stock=stock,
                            weight=weight,
                            ratings=ratings,
                            popular=popular,
                            free_delivery=free_delivery,
                            hot_deals=hot_deals,
                            flash_sale=flash_sale,
                            isOTC=isOTC,
                            image=image,
                            vendor=vendor,
                        )
                        print(f"Created item: {title}")
                    except IntegrityError:
                        print(f"Item '{title}' already exists, skipping...")
                    except Exception as e:
                        print(f"Error creating '{title}': {e}")

    print("\nAll dummy items created successfully!\n")
