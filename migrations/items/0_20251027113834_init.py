from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "category" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" VARCHAR(100) NOT NULL UNIQUE,
    "type" VARCHAR(20) NOT NULL DEFAULT 'book',
    "avatar" VARCHAR(500),
    "description" TEXT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "item" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "slug" VARCHAR(255) NOT NULL UNIQUE,
    "title" VARCHAR(255) NOT NULL,
    "short_bio" TEXT,
    "description" TEXT,
    "price" VARCHAR(40) NOT NULL DEFAULT 0,
    "discount" VARCHAR(40) NOT NULL DEFAULT 0,
    "tag" VARCHAR(2000),
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "subcategory" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" VARCHAR(100) NOT NULL,
    "avatar" VARCHAR(500),
    "description" TEXT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "category_id" INT NOT NULL REFERENCES "category" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_subcategory_categor_62a331" UNIQUE ("category_id", "name")
);
CREATE TABLE IF NOT EXISTS "subsubcategory" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" VARCHAR(100) NOT NULL,
    "avatar" VARCHAR(500),
    "description" TEXT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "subcategory_id" INT NOT NULL REFERENCES "subcategory" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_subsubcateg_subcate_05a057" UNIQUE ("subcategory_id", "name")
);
CREATE TABLE IF NOT EXISTS "group" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" VARCHAR(100) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS "permission" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" VARCHAR(100) NOT NULL UNIQUE,
    "codename" VARCHAR(100) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS "users" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "email" VARCHAR(100) UNIQUE,
    "phone" VARCHAR(20) NOT NULL UNIQUE,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "name" VARCHAR(50),
    "is_rider" INT NOT NULL DEFAULT 0,
    "is_vendor" INT NOT NULL DEFAULT 0,
    "is_active" INT NOT NULL DEFAULT 1,
    "is_staff" INT NOT NULL DEFAULT 0,
    "is_superuser" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "itemreview" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "rating" INT NOT NULL,
    "comment" TEXT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "item_id" INT NOT NULL REFERENCES "item" ("id") ON DELETE CASCADE,
    "parent_id" INT REFERENCES "itemreview" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "profiles" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "first_name" VARCHAR(50),
    "last_name" VARCHAR(50),
    "bio" TEXT,
    "photo" VARCHAR(255),
    "banner" VARCHAR(255),
    "user_id" INT NOT NULL UNIQUE REFERENCES "users" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS "group_permissions" (
    "group_id" INT NOT NULL REFERENCES "group" ("id") ON DELETE CASCADE,
    "permission_id" INT NOT NULL REFERENCES "permission" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_group_permi_group_i_c7a36c" ON "group_permissions" ("group_id", "permission_id");
CREATE TABLE IF NOT EXISTS "user_groups" (
    "users_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "group_id" INT NOT NULL REFERENCES "group" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_user_groups_users_i_7ef143" ON "user_groups" ("users_id", "group_id");
CREATE TABLE IF NOT EXISTS "user_permissions" (
    "users_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "permission_id" INT NOT NULL REFERENCES "permission" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_user_permis_users_i_035bf3" ON "user_permissions" ("users_id", "permission_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
