from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `category` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE,
    `type` VARCHAR(20) NOT NULL,
    `avatar` VARCHAR(500),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `delivery_option` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `type` VARCHAR(20) NOT NULL COMMENT 'STANDARD: standard\nEXPRESS: express\nPICKUP: pickup\nURGENT: urgent',
    `title` VARCHAR(100) NOT NULL,
    `description` LONGTEXT NOT NULL,
    `price` DECIMAL(10,2) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `group` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `payment_method` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `type` VARCHAR(20) NOT NULL COMMENT 'RAZORPAY: razorpay\nCOD: cod',
    `title` VARCHAR(100) NOT NULL,
    `description` LONGTEXT,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `permission` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE,
    `codename` VARCHAR(100) NOT NULL UNIQUE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `subcategory` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `avatar` VARCHAR(500),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `category_id` INT NOT NULL,
    UNIQUE KEY `uid_subcategory_categor_62a331` (`category_id`, `name`),
    CONSTRAINT `fk_subcateg_category_09976a38` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `subsubcategory` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `avatar` VARCHAR(500),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `subcategory_id` INT NOT NULL,
    UNIQUE KEY `uid_subsubcateg_subcate_05a057` (`subcategory_id`, `name`),
    CONSTRAINT `fk_subsubca_subcateg_c9340e8d` FOREIGN KEY (`subcategory_id`) REFERENCES `subcategory` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(100) UNIQUE,
    `phone` VARCHAR(20) NOT NULL UNIQUE,
    `name` VARCHAR(50),
    `is_rider` BOOL NOT NULL DEFAULT 0,
    `is_vendor` BOOL NOT NULL DEFAULT 0,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `is_staff` BOOL NOT NULL DEFAULT 0,
    `is_superuser` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `carts` (
    `id` VARCHAR(255) NOT NULL PRIMARY KEY,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_carts_users_8002ad31` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Cart Model';
CREATE TABLE IF NOT EXISTS `item` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `title` VARCHAR(255) NOT NULL,
    `description` LONGTEXT,
    `image` VARCHAR(200),
    `price` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `discount` INT NOT NULL DEFAULT 0,
    `ratings` DOUBLE NOT NULL DEFAULT 0,
    `stock` INT NOT NULL DEFAULT 0,
    `total_sale` INT NOT NULL DEFAULT 0,
    `popular` BOOL NOT NULL DEFAULT 0,
    `free_delivery` BOOL NOT NULL DEFAULT 0,
    `hot_deals` BOOL NOT NULL DEFAULT 0,
    `flash_sale` BOOL NOT NULL DEFAULT 0,
    `weight` DOUBLE,
    `isOTC` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `category_id` INT NOT NULL,
    `sub_subcategory_id` INT,
    `subcategory_id` INT,
    `vendor_id` INT NOT NULL,
    CONSTRAINT `fk_item_category_128c2548` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_item_subsubca_c8d125e5` FOREIGN KEY (`sub_subcategory_id`) REFERENCES `subsubcategory` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_item_subcateg_3da8c8d6` FOREIGN KEY (`subcategory_id`) REFERENCES `subcategory` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_item_users_b07d002f` FOREIGN KEY (`vendor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `cart_items` (
    `id` VARCHAR(255) NOT NULL PRIMARY KEY,
    `quantity` INT NOT NULL DEFAULT 1,
    `added_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `cart_id` VARCHAR(255) NOT NULL,
    `item_id` INT NOT NULL,
    CONSTRAINT `fk_cart_ite_carts_8a16d3c4` FOREIGN KEY (`cart_id`) REFERENCES `carts` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_cart_ite_item_c5e77454` FOREIGN KEY (`item_id`) REFERENCES `item` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Cart Item Model';
CREATE TABLE IF NOT EXISTS `rider_profiles` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `driving_license` VARCHAR(100) NOT NULL,
    `nid` VARCHAR(60) NOT NULL,
    `profile_image` VARCHAR(255),
    `national_id_document` VARCHAR(255),
    `driving_license_document` VARCHAR(255),
    `vehicle_registration_document` VARCHAR(255),
    `vehicle_insurance_document` VARCHAR(255),
    `is_available` BOOL NOT NULL DEFAULT 0,
    `is_verified` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_rider_pr_users_7fc4ee46` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `vendor_profile` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `owner_name` VARCHAR(100),
    `type` VARCHAR(20) NOT NULL,
    `photo` VARCHAR(255),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `latitude` DOUBLE,
    `longitude` DOUBLE,
    `nid` VARCHAR(60) NOT NULL,
    `fassai` VARCHAR(100),
    `drug_license` VARCHAR(100),
    `kyc_status` VARCHAR(20),
    `open_time` TIME(6),
    `close_time` TIME(6),
    `user_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_vendor_p_users_1afb3bb5` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `itemreview` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `rating` INT,
    `comment` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `item_id` INT NOT NULL,
    `parent_id` INT,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_itemrevi_item_8e4546c6` FOREIGN KEY (`item_id`) REFERENCES `item` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_itemrevi_itemrevi_fa106474` FOREIGN KEY (`parent_id`) REFERENCES `itemreview` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_itemrevi_users_09d277c5` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `cus_profile` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `add1` VARCHAR(100),
    `add2` VARCHAR(100),
    `postal_code` VARCHAR(20),
    `user_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_cus_prof_users_a53e2e78` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `customer_shipping_address` (
    `id` VARCHAR(255) NOT NULL PRIMARY KEY,
    `full_name` VARCHAR(255) NOT NULL DEFAULT '',
    `address_line1` VARCHAR(500) NOT NULL DEFAULT '',
    `address_line2` VARCHAR(500) NOT NULL DEFAULT '',
    `city` VARCHAR(255),
    `state` VARCHAR(255),
    `country` VARCHAR(255),
    `postal_code` VARCHAR(20),
    `phone_number` VARCHAR(50) NOT NULL DEFAULT '',
    `email` VARCHAR(100) NOT NULL DEFAULT '',
    `is_default` BOOL NOT NULL DEFAULT 0,
    `addressType` VARCHAR(50) NOT NULL DEFAULT 'HOME',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_customer_users_b07d2bcd` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_customer_sh_user_id_573ba3` (`user_id`, `addressType`, `is_default`)
) CHARACTER SET utf8mb4 COMMENT='Shipping Address Model';
CREATE TABLE IF NOT EXISTS `orders` (
    `id` VARCHAR(255) NOT NULL PRIMARY KEY,
    `delivery_type` VARCHAR(20) COMMENT 'STANDARD: standard\nEXPRESS: express\nPICKUP: pickup\nURGENT: urgent',
    `payment_method` VARCHAR(8) COMMENT 'RAZORPAY: razorpay\nCOD: cod',
    `subtotal` DECIMAL(10,2) NOT NULL,
    `delivery_fee` DECIMAL(10,2) NOT NULL,
    `total` DECIMAL(10,2) NOT NULL,
    `coupon_code` VARCHAR(100),
    `discount` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `order_date` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `status` VARCHAR(50) NOT NULL COMMENT 'PENDING: pending\nPROCESSING: processing\nCONFIRMED: confirmed\nSHIPPED: shipped\nOUT_FOR_DELIVERY: outForDelivery\nDELIVERED: delivered\nCANCELLED: cancelled\nREFUNDED: refunded' DEFAULT 'pending',
    `transaction_id` VARCHAR(255),
    `tracking_number` VARCHAR(255),
    `estimated_delivery` DATETIME(6),
    `metadata` JSON,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `cart_id` VARCHAR(255),
    `shipping_address_id` VARCHAR(255),
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_orders_carts_d3f34b5e` FOREIGN KEY (`cart_id`) REFERENCES `carts` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_orders_customer_8d1dd01c` FOREIGN KEY (`shipping_address_id`) REFERENCES `customer_shipping_address` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_orders_users_411bb784` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_orders_status_33ec6d` (`status`),
    KEY `idx_orders_trackin_02d9a2` (`tracking_number`),
    KEY `idx_orders_user_id_f00b6a` (`user_id`)
) CHARACTER SET utf8mb4 COMMENT='Order Model';
CREATE TABLE IF NOT EXISTS `order_item` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `title` VARCHAR(500) NOT NULL,
    `price` VARCHAR(50) NOT NULL,
    `quantity` INT NOT NULL,
    `image_path` VARCHAR(1000) NOT NULL,
    `item_id_id` INT NOT NULL,
    `order_id` VARCHAR(255) NOT NULL,
    CONSTRAINT `fk_order_it_item_0f0059a5` FOREIGN KEY (`item_id_id`) REFERENCES `item` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_order_it_orders_6a76d454` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Order Item Model';
CREATE TABLE IF NOT EXISTS `complaints` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `description` LONGTEXT NOT NULL,
    `is_serious` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `order_id` VARCHAR(255),
    CONSTRAINT `fk_complain_orders_4d483f8a` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `notifications` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `message` LONGTEXT NOT NULL,
    `type` VARCHAR(50) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `is_read` BOOL NOT NULL DEFAULT 0,
    `rider_id` INT NOT NULL,
    CONSTRAINT `fk_notifica_rider_pr_cbbe05f2` FOREIGN KEY (`rider_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `order_offers` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `customer_lat` DOUBLE NOT NULL,
    `customer_lng` DOUBLE NOT NULL,
    `vendor_lat` DOUBLE NOT NULL,
    `vendor_lng` DOUBLE NOT NULL,
    `offered_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `responded_at` DATETIME(6),
    `status` VARCHAR(20) NOT NULL DEFAULT 'offered',
    `reason` LONGTEXT,
    `pickup_distance_km` DOUBLE NOT NULL,
    `pickup_time` DATETIME(6) NOT NULL,
    `eta_minutes` INT NOT NULL,
    `base_rate` DECIMAL(10,2) NOT NULL DEFAULT 44,
    `distance_bonus` DECIMAL(10,2) NOT NULL DEFAULT 0,
    `expires_at` DATETIME(6) NOT NULL,
    `accepted_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `is_on_time` BOOL,
    `is_combined` BOOL NOT NULL DEFAULT 0,
    `combined_pickups` JSON,
    `order_id` VARCHAR(255) NOT NULL,
    `rider_id` INT NOT NULL,
    CONSTRAINT `fk_order_of_orders_5721421b` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_order_of_rider_pr_70e330ff` FOREIGN KEY (`rider_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE,
    KEY `idx_order_offer_order_i_4d189a` (`order_id`, `rider_id`)
) CHARACTER SET utf8mb4 COMMENT='Records that order was offered to rider and result (accepted/rejected/timeout).';
CREATE TABLE IF NOT EXISTS `ratings` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `score` DOUBLE NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `order_id` VARCHAR(255) NOT NULL,
    CONSTRAINT `fk_ratings_orders_56cdee3b` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `rider_availability_statuses` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `is_available` BOOL NOT NULL DEFAULT 0,
    `strat_at` TIME(6),
    `end_at` TIME(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `rider_profile_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_rider_av_rider_pr_9f0cd054` FOREIGN KEY (`rider_profile_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `rider_current_locations` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `latitude` DOUBLE NOT NULL DEFAULT 0,
    `longitude` DOUBLE NOT NULL DEFAULT 0,
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `rider_profile_id` INT NOT NULL UNIQUE,
    CONSTRAINT `fk_rider_cu_rider_pr_02c665f2` FOREIGN KEY (`rider_profile_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `vehicles` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `vehicle_type` VARCHAR(30) NOT NULL,
    `model` VARCHAR(50) NOT NULL,
    `license_plate_number` VARCHAR(20) NOT NULL UNIQUE,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `rider_profile_id` INT NOT NULL,
    CONSTRAINT `fk_vehicles_rider_pr_16caa59f` FOREIGN KEY (`rider_profile_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `withdrawals` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `amount` DECIMAL(10,2) NOT NULL,
    `status` VARCHAR(50) NOT NULL DEFAULT 'pending',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `rider_id` INT NOT NULL,
    CONSTRAINT `fk_withdraw_rider_pr_5401bc44` FOREIGN KEY (`rider_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `work_days` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `date` DATE NOT NULL,
    `hours_worked` DOUBLE NOT NULL DEFAULT 0,
    `order_offer_count` INT NOT NULL DEFAULT 0,
    `is_scheduled_leave` BOOL NOT NULL DEFAULT 0,
    `rider_id` INT NOT NULL,
    UNIQUE KEY `uid_work_days_rider_i_69393d` (`rider_id`, `date`),
    CONSTRAINT `fk_work_day_rider_pr_ebf87dab` FOREIGN KEY (`rider_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `zones` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL UNIQUE,
    `description` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `rider_zone_assignments` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `assigned_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `rider_profile_id` INT NOT NULL,
    `zone_id` INT NOT NULL,
    UNIQUE KEY `uid_rider_zone__rider_p_51575b` (`rider_profile_id`, `zone_id`),
    CONSTRAINT `fk_rider_zo_rider_pr_a0358a12` FOREIGN KEY (`rider_profile_id`) REFERENCES `rider_profiles` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_rider_zo_zones_f42b1a4e` FOREIGN KEY (`zone_id`) REFERENCES `zones` (`id`) ON DELETE CASCADE
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
