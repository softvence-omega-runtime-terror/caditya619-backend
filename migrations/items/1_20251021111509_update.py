from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `category` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE,
    `avatar` VARCHAR(500),
    `description` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `subcategory` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `avatar` VARCHAR(500),
    `description` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `category_id` INT NOT NULL,
    UNIQUE KEY `uid_subcategory_categor_62a331` (`category_id`, `name`),
    CONSTRAINT `fk_subcateg_category_09976a38` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `subsubcategory` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `avatar` VARCHAR(500),
    `description` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `subcategory_id` INT NOT NULL,
    UNIQUE KEY `uid_subsubcateg_subcate_05a057` (`subcategory_id`, `name`),
    CONSTRAINT `fk_subsubca_subcateg_c9340e8d` FOREIGN KEY (`subcategory_id`) REFERENCES `subcategory` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `subsubcategory`;
        DROP TABLE IF EXISTS `subcategory`;
        DROP TABLE IF EXISTS `category`;"""
