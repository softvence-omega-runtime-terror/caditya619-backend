from fastapi_admin.app import app as admin_app
# from fastapi_admin.site import Site
from fastapi_admin.app import Site
from fastapi_admin.resources import Model
from .models import User, Group, Permission
from fastapi_admin.providers.login import UsernamePasswordProvider

async def setup_admin(app):
    site = Site(name="Admin Panel")
    
    site.register(
        Model(User),
        Model(Group),
        Model(Permission)
    )

    login_provider = UsernamePasswordProvider(admin_model=User, username_field="username")
    site.register_provider(login_provider)

    await admin_app.configure(site)
