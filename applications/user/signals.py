from tortoise.signals import post_save
from applications.user.models import User, CustomerProfile, VendorProfile, RiderProfile

async def create_user_profile(sender, instance: User, created: bool, **kwargs):
    if created:
        # profile = CustomerProfile(user=instance)
        # await profile.save()
        print(f"✅ Profile created for user")

post_save(User)(create_user_profile)