from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `brand_vid` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `type` VARCHAR(20) NOT NULL COMMENT 'Select the type of video source' DEFAULT 'youtube',
    `video_id` VARCHAR(400) NOT NULL COMMENT 'YouTube video ID or Cloudinary video ID',
    `title` LONGTEXT COMMENT 'Title of the video',
    `description` LONGTEXT COMMENT 'Description of the video',
    `autoplay` VARCHAR(20) NOT NULL COMMENT 'Autoplay mode: false, true, on-scroll' DEFAULT 'false',
    `muted` BOOL NOT NULL DEFAULT 1,
    `controls` BOOL NOT NULL DEFAULT 1,
    `loop` BOOL NOT NULL DEFAULT 0,
    `playlist` BOOL NOT NULL DEFAULT 0,
    `endScreen` BOOL NOT NULL DEFAULT 1,
    `pip` BOOL NOT NULL COMMENT 'Picture in Picture Mode' DEFAULT 0,
    `poster` VARCHAR(500) COMMENT 'Poster image path',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
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
CREATE TABLE IF NOT EXISTS `book` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `title` VARCHAR(255) NOT NULL,
    `slug` VARCHAR(255) NOT NULL UNIQUE,
    `description` LONGTEXT,
    `price` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `discount` DECIMAL(5,2) NOT NULL DEFAULT 0,
    `box_price` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `stock` INT NOT NULL DEFAULT 0,
    `popular` BOOL NOT NULL DEFAULT 0,
    `free_delivery` BOOL NOT NULL DEFAULT 0,
    `hot_deals` BOOL NOT NULL DEFAULT 0,
    `flash_sale` BOOL NOT NULL DEFAULT 0,
    `tag` VARCHAR(2000) DEFAULT 'academic_books',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `book_type` VARCHAR(50) NOT NULL DEFAULT 'academic_book',
    `author` VARCHAR(255) NOT NULL,
    `publisher` VARCHAR(255),
    `isbn` VARCHAR(13) UNIQUE,
    `edition` VARCHAR(50),
    `total_pages` INT,
    `language` VARCHAR(50),
    `publication_date` DATETIME(6),
    `file_sample` VARCHAR(500),
    `file_full` VARCHAR(500),
    `image` VARCHAR(500),
    `category_id` INT NOT NULL,
    `subcategory_id` INT,
    CONSTRAINT `fk_book_category_55ad78a4` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_book_subcateg_2606e58c` FOREIGN KEY (`subcategory_id`) REFERENCES `subcategory` (`id`) ON DELETE SET NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `item` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `title` VARCHAR(255) NOT NULL,
    `slug` VARCHAR(255) NOT NULL UNIQUE,
    `description` LONGTEXT,
    `price` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `discount` DECIMAL(5,2) NOT NULL DEFAULT 0,
    `box_price` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `stock` INT NOT NULL DEFAULT 0,
    `popular` BOOL NOT NULL DEFAULT 0,
    `free_delivery` BOOL NOT NULL DEFAULT 0,
    `hot_deals` BOOL NOT NULL DEFAULT 0,
    `flash_sale` BOOL NOT NULL DEFAULT 0,
    `tag` VARCHAR(2000) DEFAULT 'academic_books',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `itemreview` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `rating` INT NOT NULL,
    `comment` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `item_id` INT NOT NULL,
    CONSTRAINT `fk_itemrevi_item_8e4546c6` FOREIGN KEY (`item_id`) REFERENCES `item` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `group` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `permission` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE,
    `codename` VARCHAR(100) NOT NULL UNIQUE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(100) UNIQUE,
    `phone` VARCHAR(20) UNIQUE,
    `username` VARCHAR(50) NOT NULL UNIQUE,
    `password` VARCHAR(128) NOT NULL,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `is_staff` BOOL NOT NULL DEFAULT 0,
    `is_superuser` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `profiles` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `first_name` VARCHAR(50),
    `last_name` VARCHAR(50),
    `bio` LONGTEXT,
    `photo` VARCHAR(255),
    `banner` VARCHAR(255),
    `user_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_profiles_users_1fa64c78` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `group_permissions` (
    `group_id` INT NOT NULL,
    `permission_id` INT NOT NULL,
    FOREIGN KEY (`group_id`) REFERENCES `group` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`permission_id`) REFERENCES `permission` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_group_permi_group_i_c7a36c` (`group_id`, `permission_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_groups` (
    `users_id` INT NOT NULL,
    `group_id` INT NOT NULL,
    FOREIGN KEY (`users_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`group_id`) REFERENCES `group` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_user_groups_users_i_7ef143` (`users_id`, `group_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_permissions` (
    `users_id` INT NOT NULL,
    `permission_id` INT NOT NULL,
    FOREIGN KEY (`users_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`permission_id`) REFERENCES `permission` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_user_permis_users_i_035bf3` (`users_id`, `permission_id`)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
