from tortoise.exceptions import IntegrityError
from applications.user.models import User, RiderProfile, CustomerProfile, VendorProfile

USERS_DATA = [
    {
        "phone": "+919876543210",
        "email": "admin@gmail.com",
        "name": "Admin User",
        "is_rider": True,
        "is_vendor": True,
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "phone": "+919876543211",
        "email": "rider1@gmail.com",
        "name": "Rider One",
        "is_rider": True,
    },
    {
        "phone": "+919876543212",
        "email": "vendor1@gmail.com",
        "name": "Vendor One",
        "is_vendor": True,
    },
    {
        "phone": "+919876543213",
        "email": "mix1@gmail.com",
        "name": "Mix One",
        "is_rider": True,
        "is_vendor": True,
    },
    {
        "phone": "+919876543214",
        "email": "staff1@gmail.com",
        "name": "Staff One",
        "is_staff": True,
    },
    {
        "phone": "+919876543215",
        "email": "rider2@gmail.com",
        "name": "Rider Two",
        "is_rider": True,
    },
    {
        "phone": "+919876543216",
        "email": "vendor2@gmail.com",
        "name": "Vendor Two",
        "is_vendor": True,
    },
    {
        "phone": "+919876543217",
        "email": "mix2@gmail.com",
        "name": "Mix Two",
        "is_rider": True,
        "is_vendor": True,
    },
    {
        "phone": "+919876543218",
        "email": "staff2@gmail.com",
        "name": "Staff Two",
        "is_staff": True,
    },
    {
        "phone": "+919876543219",
        "email": "test10@gmail.com",
        "name": "Test Ten",
        "is_rider": True,
    },
]


async def create_test_users():
    """
    Creates test users and automatically generates related profiles
    based on user role flags.
    """
    for data in USERS_DATA:
        phone = data["phone"]

        # Skip if already exists
        existing = await User.filter(phone=phone).first()
        if existing:
            print(f"⚠️ User with phone {phone} already exists — skipping.")
            continue

        try:
            # Create user
            user = await User.create(**data)
            print(f"✅ Created user: {user.name} ({user.phone})")

            # Always create a CustomerProfile
            await CustomerProfile.get_or_create(user=user)

            # Conditionally create RiderProfile
            if user.is_rider:
                await RiderProfile.get_or_create(
                    user=user,
                    defaults={
                        "driving_license": f"DL-{user.phone[-4:]}",
                        "nid": f"NID-{user.phone[-6:]}"
                    }
                )
                print(f"   🏍️ RiderProfile created for {user.phone}")

            # Conditionally create VendorProfile
            if user.is_vendor:
                await VendorProfile.get_or_create(
                    user=user,
                    defaults={
                        "nid": f"VNID-{user.phone[-6:]}"
                    }
                )
                print(f"   🏬 VendorProfile created for {user.phone}")

        except IntegrityError as e:
            print(f"❌ Error creating user {phone}: {e}")
        except Exception as e:
            print(f"⚠️ Unexpected error for {phone}: {e}")

    print("\n🎉 All test users and profiles created successfully!")
