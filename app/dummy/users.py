from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from applications.user.models import User
from applications.user.rider import RiderProfile
from applications.user.vendor import VendorProfile
from applications.user.customer import CustomerProfile

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
    # 10 vendor users with different types
    {"phone": "+919876543212", "email": "vendor1@gmail.com", "name": "Vendor One", "is_vendor": True, "vendor_type": "food"},
    {"phone": "+919876543213", "email": "vendor2@gmail.com", "name": "Vendor Two", "is_vendor": True, "vendor_type": "grocery"},
    {"phone": "+919876543214", "email": "vendor3@gmail.com", "name": "Vendor Three", "is_vendor": True, "vendor_type": "medicine"},
    {"phone": "+919876543215", "email": "vendor4@gmail.com", "name": "Vendor Four", "is_vendor": True, "vendor_type": "food"},
    {"phone": "+919876543216", "email": "vendor5@gmail.com", "name": "Vendor Five", "is_vendor": True, "vendor_type": "grocery"},
    {"phone": "+919876543217", "email": "vendor6@gmail.com", "name": "Vendor Six", "is_vendor": True, "vendor_type": "medicine"},
    {"phone": "+919876543218", "email": "vendor7@gmail.com", "name": "Vendor Seven", "is_vendor": True, "vendor_type": "food"},
    {"phone": "+919876543219", "email": "vendor8@gmail.com", "name": "Vendor Eight", "is_vendor": True, "vendor_type": "grocery"},
    {"phone": "+919876543220", "email": "vendor9@gmail.com", "name": "Vendor Nine", "is_vendor": True, "vendor_type": "medicine"},
    {"phone": "+919876543221", "email": "vendor10@gmail.com", "name": "Vendor Ten", "is_vendor": True, "vendor_type": "food"},
    # Riders or mix users
    {"phone": "+919876543222", "email": "rider2@gmail.com", "name": "Rider Two", "is_rider": True},
    {"phone": "+919876543223", "email": "mix1@gmail.com", "name": "Mix One", "is_rider": True, "is_vendor": True, "vendor_type": "grocery"},
]

async def create_test_users():
    for data in USERS_DATA:
        phone = data["phone"]
        vendor_type = data.pop("vendor_type", "grocery")  # default type if not specified

        try:
            async with in_transaction() as conn:
                # Create or get the user
                user, created = await User.get_or_create(
                    phone=phone, defaults=data, using_db=conn
                )

                # Update flags if user exists
                update_needed = False
                for flag in ["is_rider", "is_vendor", "is_staff", "is_superuser"]:
                    if getattr(user, flag) != data.get(flag, False):
                        setattr(user, flag, data.get(flag, False))
                        update_needed = True
                if update_needed:
                    await user.save(using_db=conn)

                if created:
                    print(f"✅ Created user: {user.name} ({user.phone})")
                else:
                    print(f"⚠️ User with phone {user.phone} already exists — updated flags if needed.")

                # Ensure CustomerProfile
                await CustomerProfile.get_or_create(user=user, using_db=conn)
                print(f"   👤 CustomerProfile ensured for {user.phone}")

                # Ensure RiderProfile
                if data.get("is_rider"):
                    await RiderProfile.get_or_create(
                        user=user,
                        defaults={
                            "driving_license": f"DL-{user.phone[-4:]}",
                            "nid": f"NID-{user.phone[-6:]}",
                        },
                        using_db=conn,
                    )
                    print(f"   🏍️ RiderProfile ensured for {user.phone}")

                # Ensure VendorProfile
                if data.get("is_vendor"):
                    await VendorProfile.get_or_create(
                        user=user,
                        defaults={
                            "nid": f"VNID-{user.phone[-6:]}",
                            "type": vendor_type,
                        },
                        using_db=conn,
                    )
                    print(f"   🏬 VendorProfile ensured for {user.phone} with type '{vendor_type}'")

        except IntegrityError as e:
            print(f"❌ IntegrityError creating user {phone}: {e}")
        except Exception as e:
            print(f"⚠️ Unexpected error for {phone}: {e}")

    print("\n🎉 All test users and profiles created/ensured successfully!")
