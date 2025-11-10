from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from applications.items.models import Category, SubCategory, SubSubCategory


# Each category has subcategories, and each subcategory has its own sub-subcategories
SUBCATEGORIES_DATA = {
    "Food": [
        {
            "name": "Snacks",
            "avatar": "https://via.placeholder.com/300x300?text=Snacks",
            "sub_subcategories": [
                {"name": "Chips", "avatar": "https://via.placeholder.com/300x300?text=Chips"},
                {"name": "Biscuits", "avatar": "https://via.placeholder.com/300x300?text=Biscuits"},
                {"name": "Nuts", "avatar": "https://via.placeholder.com/300x300?text=Nuts"},
                {"name": "Popcorn", "avatar": "https://via.placeholder.com/300x300?text=Popcorn"},
                {"name": "Cookies", "avatar": "https://via.placeholder.com/300x300?text=Cookies"},
            ]
        },
        {
            "name": "Beverages",
            "avatar": "https://via.placeholder.com/300x300?text=Beverages",
            "sub_subcategories": [
                {"name": "Juices", "avatar": "https://via.placeholder.com/300x300?text=Juices"},
                {"name": "Sodas", "avatar": "https://via.placeholder.com/300x300?text=Sodas"},
                {"name": "Energy Drinks", "avatar": "https://via.placeholder.com/300x300?text=Energy+Drinks"},
                {"name": "Tea & Coffee", "avatar": "https://via.placeholder.com/300x300?text=Tea+%26+Coffee"},
                {"name": "Water", "avatar": "https://via.placeholder.com/300x300?text=Water"},
            ]
        },
        {
            "name": "Frozen Food",
            "avatar": "https://via.placeholder.com/300x300?text=Frozen+Food",
            "sub_subcategories": [
                {"name": "Vegetables", "avatar": "https://via.placeholder.com/300x300?text=Vegetables"},
                {"name": "Meat", "avatar": "https://via.placeholder.com/300x300?text=Meat"},
                {"name": "Seafood", "avatar": "https://via.placeholder.com/300x300?text=Seafood"},
                {"name": "Pizza", "avatar": "https://via.placeholder.com/300x300?text=Pizza"},
                {"name": "Ice Cream", "avatar": "https://via.placeholder.com/300x300?text=Ice+Cream"},
            ]
        },
        {
            "name": "Bakery",
            "avatar": "https://via.placeholder.com/300x300?text=Bakery",
            "sub_subcategories": [
                {"name": "Bread", "avatar": "https://via.placeholder.com/300x300?text=Bread"},
                {"name": "Cakes", "avatar": "https://via.placeholder.com/300x300?text=Cakes"},
                {"name": "Pastries", "avatar": "https://via.placeholder.com/300x300?text=Pastries"},
                {"name": "Croissants", "avatar": "https://via.placeholder.com/300x300?text=Croissants"},
                {"name": "Muffins", "avatar": "https://via.placeholder.com/300x300?text=Muffins"},
            ]
        },
        {
            "name": "Canned Goods",
            "avatar": "https://via.placeholder.com/300x300?text=Canned+Goods",
            "sub_subcategories": [
                {"name": "Beans", "avatar": "https://via.placeholder.com/300x300?text=Beans"},
                {"name": "Fruits", "avatar": "https://via.placeholder.com/300x300?text=Fruits"},
                {"name": "Vegetables", "avatar": "https://via.placeholder.com/300x300?text=Vegetables"},
                {"name": "Soups", "avatar": "https://via.placeholder.com/300x300?text=Soups"},
                {"name": "Sauces", "avatar": "https://via.placeholder.com/300x300?text=Sauces"},
            ]
        },
    ],
    "Groceries": [
        {
            "name": "Rice & Grains",
            "avatar": "https://via.placeholder.com/300x300?text=Rice+%26+Grains",
            "sub_subcategories": [
                {"name": "Basmati", "avatar": "https://via.placeholder.com/300x300?text=Basmati"},
                {"name": "Brown Rice", "avatar": "https://via.placeholder.com/300x300?text=Brown+Rice"},
                {"name": "Oats", "avatar": "https://via.placeholder.com/300x300?text=Oats"},
                {"name": "Quinoa", "avatar": "https://via.placeholder.com/300x300?text=Quinoa"},
                {"name": "Barley", "avatar": "https://via.placeholder.com/300x300?text=Barley"},
            ]
        },
        {
            "name": "Cooking Oil",
            "avatar": "https://via.placeholder.com/300x300?text=Cooking+Oil",
            "sub_subcategories": [
                {"name": "Olive Oil", "avatar": "https://via.placeholder.com/300x300?text=Olive+Oil"},
                {"name": "Sunflower Oil", "avatar": "https://via.placeholder.com/300x300?text=Sunflower+Oil"},
                {"name": "Vegetable Oil", "avatar": "https://via.placeholder.com/300x300?text=Vegetable+Oil"},
                {"name": "Coconut Oil", "avatar": "https://via.placeholder.com/300x300?text=Coconut+Oil"},
                {"name": "Canola Oil", "avatar": "https://via.placeholder.com/300x300?text=Canola+Oil"},
            ]
        },
        {
            "name": "Sugar & Salt",
            "avatar": "https://via.placeholder.com/300x300?text=Sugar+%26+Salt",
            "sub_subcategories": [
                {"name": "White Sugar", "avatar": "https://via.placeholder.com/300x300?text=White+Sugar"},
                {"name": "Brown Sugar", "avatar": "https://via.placeholder.com/300x300?text=Brown+Sugar"},
                {"name": "Sea Salt", "avatar": "https://via.placeholder.com/300x300?text=Sea+Salt"},
                {"name": "Iodized Salt", "avatar": "https://via.placeholder.com/300x300?text=Iodized+Salt"},
                {"name": "Rock Salt", "avatar": "https://via.placeholder.com/300x300?text=Rock+Salt"},
            ]
        },
        {
            "name": "Dry Fruits",
            "avatar": "https://via.placeholder.com/300x300?text=Dry+Fruits",
            "sub_subcategories": [
                {"name": "Almonds", "avatar": "https://via.placeholder.com/300x300?text=Almonds"},
                {"name": "Cashews", "avatar": "https://via.placeholder.com/300x300?text=Cashews"},
                {"name": "Walnuts", "avatar": "https://via.placeholder.com/300x300?text=Walnuts"},
                {"name": "Raisins", "avatar": "https://via.placeholder.com/300x300?text=Raisins"},
                {"name": "Pistachios", "avatar": "https://via.placeholder.com/300x300?text=Pistachios"},
            ]
        },
        {
            "name": "Condiments",
            "avatar": "https://via.placeholder.com/300x300?text=Condiments",
            "sub_subcategories": [
                {"name": "Ketchup", "avatar": "https://via.placeholder.com/300x300?text=Ketchup"},
                {"name": "Mustard", "avatar": "https://via.placeholder.com/300x300?text=Mustard"},
                {"name": "Mayonnaise", "avatar": "https://via.placeholder.com/300x300?text=Mayonnaise"},
                {"name": "Vinegar", "avatar": "https://via.placeholder.com/300x300?text=Vinegar"},
                {"name": "Soy Sauce", "avatar": "https://via.placeholder.com/300x300?text=Soy+Sauce"},
            ]
        },
    ],
    "Medicine": [
        {
            "name": "Vitamins",
            "avatar": "https://via.placeholder.com/300x300?text=Vitamins",
            "sub_subcategories": [
                {"name": "Vitamin A", "avatar": "https://via.placeholder.com/300x300?text=Vitamin+A"},
                {"name": "Vitamin B", "avatar": "https://via.placeholder.com/300x300?text=Vitamin+B"},
                {"name": "Vitamin C", "avatar": "https://via.placeholder.com/300x300?text=Vitamin+C"},
                {"name": "Vitamin D", "avatar": "https://via.placeholder.com/300x300?text=Vitamin+D"},
                {"name": "Vitamin E", "avatar": "https://via.placeholder.com/300x300?text=Vitamin+E"},
            ]
        },
        {
            "name": "First Aid",
            "avatar": "https://via.placeholder.com/300x300?text=First+Aid",
            "sub_subcategories": [
                {"name": "Bandages", "avatar": "https://via.placeholder.com/300x300?text=Bandages"},
                {"name": "Antiseptics", "avatar": "https://via.placeholder.com/300x300?text=Antiseptics"},
                {"name": "Gauze", "avatar": "https://via.placeholder.com/300x300?text=Gauze"},
                {"name": "Cotton", "avatar": "https://via.placeholder.com/300x300?text=Cotton"},
                {"name": "Medical Tape", "avatar": "https://via.placeholder.com/300x300?text=Medical+Tape"},
            ]
        },
        {
            "name": "Pain Relief",
            "avatar": "https://via.placeholder.com/300x300?text=Pain+Relief",
            "sub_subcategories": [
                {"name": "Paracetamol", "avatar": "https://via.placeholder.com/300x300?text=Paracetamol"},
                {"name": "Ibuprofen", "avatar": "https://via.placeholder.com/300x300?text=Ibuprofen"},
                {"name": "Aspirin", "avatar": "https://via.placeholder.com/300x300?text=Aspirin"},
                {"name": "Diclofenac", "avatar": "https://via.placeholder.com/300x300?text=Diclofenac"},
                {"name": "Naproxen", "avatar": "https://via.placeholder.com/300x300?text=Naproxen"},
            ]
        },
        {
            "name": "Cold & Flu",
            "avatar": "https://via.placeholder.com/300x300?text=Cold+%26+Flu",
            "sub_subcategories": [
                {"name": "Cough Syrup", "avatar": "https://via.placeholder.com/300x300?text=Cough+Syrup"},
                {"name": "Decongestant", "avatar": "https://via.placeholder.com/300x300?text=Decongestant"},
                {"name": "Lozenges", "avatar": "https://via.placeholder.com/300x300?text=Lozenges"},
                {"name": "Nasal Spray", "avatar": "https://via.placeholder.com/300x300?text=Nasal+Spray"},
                {"name": "Antihistamines", "avatar": "https://via.placeholder.com/300x300?text=Antihistamines"},
            ]
        },
        {
            "name": "Allergy Care",
            "avatar": "https://via.placeholder.com/300x300?text=Allergy+Care",
            "sub_subcategories": [
                {"name": "Antihistamines", "avatar": "https://via.placeholder.com/300x300?text=Antihistamines"},
                {"name": "Eye Drops", "avatar": "https://via.placeholder.com/300x300?text=Eye+Drops"},
                {"name": "Nasal Spray", "avatar": "https://via.placeholder.com/300x300?text=Nasal+Spray"},
                {"name": "Creams", "avatar": "https://via.placeholder.com/300x300?text=Creams"},
                {"name": "Oral Medicine", "avatar": "https://via.placeholder.com/300x300?text=Oral+Medicine"},
            ]
        },
    ],
    "Cleaning": [
        {
            "name": "Laundry",
            "avatar": "https://via.placeholder.com/300x300?text=Laundry",
            "sub_subcategories": [
                {"name": "Detergents", "avatar": "https://via.placeholder.com/300x300?text=Detergents"},
                {"name": "Fabric Softener", "avatar": "https://via.placeholder.com/300x300?text=Fabric+Softener"},
                {"name": "Bleach", "avatar": "https://via.placeholder.com/300x300?text=Bleach"},
                {"name": "Stain Remover", "avatar": "https://via.placeholder.com/300x300?text=Stain+Remover"},
                {"name": "Laundry Bags", "avatar": "https://via.placeholder.com/300x300?text=Laundry+Bags"},
            ]
        },
        {
            "name": "Household Cleaning",
            "avatar": "https://via.placeholder.com/300x300?text=Household+Cleaning",
            "sub_subcategories": [
                {"name": "Floor Cleaner", "avatar": "https://via.placeholder.com/300x300?text=Floor+Cleaner"},
                {"name": "Glass Cleaner", "avatar": "https://via.placeholder.com/300x300?text=Glass+Cleaner"},
                {"name": "Dishwashing", "avatar": "https://via.placeholder.com/300x300?text=Dishwashing"},
                {"name": "Disinfectants", "avatar": "https://via.placeholder.com/300x300?text=Disinfectants"},
                {"name": "Sponges & Scrubbers", "avatar": "https://via.placeholder.com/300x300?text=Sponges+%26+Scrubbers"},
            ]
        },
        {
            "name": "Pest Control",
            "avatar": "https://via.placeholder.com/300x300?text=Pest+Control",
            "sub_subcategories": [
                {"name": "Insecticides", "avatar": "https://via.placeholder.com/300x300?text=Insecticides"},
                {"name": "Rodenticides", "avatar": "https://via.placeholder.com/300x300?text=Rodenticides"},
                {"name": "Mosquito Repellent", "avatar": "https://via.placeholder.com/300x300?text=Mosquito+Repellent"},
                {"name": "Traps", "avatar": "https://via.placeholder.com/300x300?text=Traps"},
                {"name": "Fumigators", "avatar": "https://via.placeholder.com/300x300?text=Fumigators"},
            ]
        },
        {
            "name": "Paper Products",
            "avatar": "https://via.placeholder.com/300x300?text=Paper+Products",
            "sub_subcategories": [
                {"name": "Toilet Paper", "avatar": "https://via.placeholder.com/300x300?text=Toilet+Paper"},
                {"name": "Tissues", "avatar": "https://via.placeholder.com/300x300?text=Tissues"},
                {"name": "Paper Towels", "avatar": "https://via.placeholder.com/300x300?text=Paper+Towels"},
                {"name": "Napkins", "avatar": "https://via.placeholder.com/300x300?text=Napkins"},
                {"name": "Cleaning Wipes", "avatar": "https://via.placeholder.com/300x300?text=Cleaning+Wipes"},
            ]
        },
        {
            "name": "Air Fresheners",
            "avatar": "https://via.placeholder.com/300x300?text=Air+Fresheners",
            "sub_subcategories": [
                {"name": "Sprays", "avatar": "https://via.placeholder.com/300x300?text=Sprays"},
                {"name": "Diffusers", "avatar": "https://via.placeholder.com/300x300?text=Diffusers"},
                {"name": "Candles", "avatar": "https://via.placeholder.com/300x300?text=Candles"},
                {"name": "Plug-ins", "avatar": "https://via.placeholder.com/300x300?text=Plug-ins"},
                {"name": "Gel Fresheners", "avatar": "https://via.placeholder.com/300x300?text=Gel+Fresheners"},
            ]
        },
    ],
    "Personal Care": [
        {
            "name": "Oral Care",
            "avatar": "https://via.placeholder.com/300x300?text=Oral+Care",
            "sub_subcategories": [
                {"name": "Toothpaste", "avatar": "https://via.placeholder.com/300x300?text=Toothpaste"},
                {"name": "Toothbrush", "avatar": "https://via.placeholder.com/300x300?text=Toothbrush"},
                {"name": "Mouthwash", "avatar": "https://via.placeholder.com/300x300?text=Mouthwash"},
                {"name": "Floss", "avatar": "https://via.placeholder.com/300x300?text=Floss"},
                {"name": "Whitening Kits", "avatar": "https://via.placeholder.com/300x300?text=Whitening+Kits"},
            ]
        },
        {
            "name": "Hair Care",
            "avatar": "https://via.placeholder.com/300x300?text=Hair+Care",
            "sub_subcategories": [
                {"name": "Shampoo", "avatar": "https://via.placeholder.com/300x300?text=Shampoo"},
                {"name": "Conditioner", "avatar": "https://via.placeholder.com/300x300?text=Conditioner"},
                {"name": "Hair Oil", "avatar": "https://via.placeholder.com/300x300?text=Hair+Oil"},
                {"name": "Hair Color", "avatar": "https://via.placeholder.com/300x300?text=Hair+Color"},
                {"name": "Hair Serum", "avatar": "https://via.placeholder.com/300x300?text=Hair+Serum"},
            ]
        },
        {
            "name": "Skin Care",
            "avatar": "https://via.placeholder.com/300x300?text=Skin+Care",
            "sub_subcategories": [
                {"name": "Moisturizers", "avatar": "https://via.placeholder.com/300x300?text=Moisturizers"},
                {"name": "Cleansers", "avatar": "https://via.placeholder.com/300x300?text=Cleansers"},
                {"name": "Face Masks", "avatar": "https://via.placeholder.com/300x300?text=Face+Masks"},
                {"name": "Sunscreen", "avatar": "https://via.placeholder.com/300x300?text=Sunscreen"},
                {"name": "Exfoliators", "avatar": "https://via.placeholder.com/300x300?text=Exfoliators"},
            ]
        },
        {
            "name": "Bath & Body",
            "avatar": "https://via.placeholder.com/300x300?text=Bath+%26+Body",
            "sub_subcategories": [
                {"name": "Soaps", "avatar": "https://via.placeholder.com/300x300?text=Soaps"},
                {"name": "Body Wash", "avatar": "https://via.placeholder.com/300x300?text=Body+Wash"},
                {"name": "Scrubs", "avatar": "https://via.placeholder.com/300x300?text=Scrubs"},
                {"name": "Lotions", "avatar": "https://via.placeholder.com/300x300?text=Lotions"},
                {"name": "Deodorants", "avatar": "https://via.placeholder.com/300x300?text=Deodorants"},
            ]
        },
        {
            "name": "Shaving & Grooming",
            "avatar": "https://via.placeholder.com/300x300?text=Shaving+%26+Grooming",
            "sub_subcategories": [
                {"name": "Razor Blades", "avatar": "https://via.placeholder.com/300x300?text=Razor+Blades"},
                {"name": "Shaving Cream", "avatar": "https://via.placeholder.com/300x300?text=Shaving+Cream"},
                {"name": "Aftershave", "avatar": "https://via.placeholder.com/300x300?text=Aftershave"},
                {"name": "Beard Oil", "avatar": "https://via.placeholder.com/300x300?text=Beard+Oil"},
                {"name": "Trimmers", "avatar": "https://via.placeholder.com/300x300?text=Trimmers"},
            ]
        },
    ],
    "Pet Supplies": [
        {
            "name": "Pet Food",
            "avatar": "https://via.placeholder.com/300x300?text=Pet+Food",
            "sub_subcategories": [
                {"name": "Dog Food", "avatar": "https://via.placeholder.com/300x300?text=Dog+Food"},
                {"name": "Cat Food", "avatar": "https://via.placeholder.com/300x300?text=Cat+Food"},
                {"name": "Bird Food", "avatar": "https://via.placeholder.com/300x300?text=Bird+Food"},
                {"name": "Fish Food", "avatar": "https://via.placeholder.com/300x300?text=Fish+Food"},
                {"name": "Small Pet Food", "avatar": "https://via.placeholder.com/300x300?text=Small+Pet+Food"},
            ]
        },
        {
            "name": "Pet Accessories",
            "avatar": "https://via.placeholder.com/300x300?text=Pet+Accessories",
            "sub_subcategories": [
                {"name": "Collars", "avatar": "https://via.placeholder.com/300x300?text=Collars"},
                {"name": "Leashes", "avatar": "https://via.placeholder.com/300x300?text=Leashes"},
                {"name": "Beds", "avatar": "https://via.placeholder.com/300x300?text=Beds"},
                {"name": "Toys", "avatar": "https://via.placeholder.com/300x300?text=Toys"},
                {"name": "Bowls & Feeders", "avatar": "https://via.placeholder.com/300x300?text=Bowls+%26+Feeders"},
            ]
        },
        {
            "name": "Pet Care",
            "avatar": "https://via.placeholder.com/300x300?text=Pet+Care",
            "sub_subcategories": [
                {"name": "Shampoos", "avatar": "https://via.placeholder.com/300x300?text=Shampoos"},
                {"name": "Flea & Tick", "avatar": "https://via.placeholder.com/300x300?text=Flea+%26+Tick"},
                {"name": "Grooming Tools", "avatar": "https://via.placeholder.com/300x300?text=Grooming+Tools"},
                {"name": "Vitamins", "avatar": "https://via.placeholder.com/300x300?text=Vitamins"},
                {"name": "Dental Care", "avatar": "https://via.placeholder.com/300x300?text=Dental+Care"},
            ]
        },
    ],
}


async def create_test_subcategories():
    for category_name, subcategories in SUBCATEGORIES_DATA.items():
        category = await Category.filter(name=category_name).first()
        if not category:
            print(f"⚠️ Category '{category_name}' not found. Skipping...")
            continue

        print(f"\nProcessing category: {category_name}")

        for sub_data in subcategories:
            sub_name = sub_data["name"]
            avatar = sub_data.get("avatar")
            sub_subs = sub_data.get("sub_subcategories", [])

            async with in_transaction() as connection:
                try:
                    sub = await SubCategory.filter(category=category, name=sub_name).using_db(connection).first()
                    if not sub:
                        sub = await SubCategory.create(
                            category=category,
                            name=sub_name,
                            avatar=avatar,
                            using_db=connection,
                        )
                        print(f"✅ Created subcategory: {sub.name} under {category.name}")

                    # Create sub-subcategories for this subcategory
                    for subsub_data in sub_subs:
                        exists = await SubSubCategory.filter(
                            subcategory=sub, name=subsub_data["name"]
                        ).using_db(connection).first()
                        if exists:
                            continue

                        await SubSubCategory.create(
                            subcategory=sub,
                            name=subsub_data["name"],
                            avatar=subsub_data.get("avatar"),
                            using_db=connection,
                        )
                    print(f"   ↳ Created {len(sub_subs)} sub-subcategories for {sub.name}")

                except IntegrityError as e:
                    await connection.rollback()
                    print(f"⚠️ IntegrityError in {sub_name}: {e}")
                except Exception as e:
                    await connection.rollback()
                    print(f"❌ Unexpected error in {sub_name}: {e}")

    print("\n🎉 All subcategories and sub-subcategories created successfully!\n")
