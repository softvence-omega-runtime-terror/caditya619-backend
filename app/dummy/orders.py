import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple
from uuid import uuid4

from applications.customer.models import (
    DeliveryTypeEnum,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethodType,
)
from applications.items.models import Category, Item
from applications.user.models import User
from applications.user.vendor import VendorProfile


MONEY_Q = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _random_order_timestamps(now: datetime) -> Tuple[datetime, datetime, datetime]:
    # Spread timestamps across the last 21 days.
    created_at = now - timedelta(
        days=random.randint(0, 20),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )

    completed_at = created_at + timedelta(
        hours=random.randint(1, 48),
        minutes=random.randint(0, 59),
    )
    if completed_at > now:
        completed_at = now - timedelta(minutes=random.randint(1, 30))
    if completed_at < created_at:
        completed_at = created_at + timedelta(minutes=10)

    updated_at = completed_at + timedelta(
        minutes=random.randint(1, 240),
    )
    if updated_at > now:
        updated_at = now - timedelta(minutes=random.randint(0, 15))
    if updated_at < completed_at:
        updated_at = completed_at

    return created_at, completed_at, updated_at


async def _apply_last_3_weeks_timestamps(order_id: str):
    now = datetime.now(timezone.utc)
    created_at, completed_at, updated_at = _random_order_timestamps(now)

    await Order.filter(id=order_id).update(
        created_at=created_at,
        order_date=created_at,
        completed_at=completed_at,
        updated_at=updated_at,
    )


async def _ensure_vendor_has_item(vendor: User) -> Item:
    existing = await Item.filter(vendor_id=vendor.id).first()
    if existing:
        return existing

    profile = await VendorProfile.get_or_none(user_id=vendor.id)
    vendor_type = getattr(profile, "type", "grocery")

    category = await Category.filter(type=vendor_type).first()
    if not category:
        category_name = f"Dummy {vendor_type.title()} Category"
        category, _ = await Category.get_or_create(
            name=category_name,
            defaults={
                "type": vendor_type,
                "avatar": "https://via.placeholder.com/300x300?text=Dummy+Category",
            },
        )

    return await Item.create(
        category_id=category.id,
        title=f"Dummy Item {vendor.id}",
        description="Auto-generated item for dummy order creation",
        image="https://via.placeholder.com/300x300?text=Dummy+Item",
        price=Decimal("100.00"),
        discount=0,
        stock=100,
        vendor_id=vendor.id,
        weight=1.0,
        ratings=4.5,
    )


async def create_dummy_orders_for_all_vendors(per_vendor: int = 20):
    vendors = await User.filter(is_vendor=True).all()
    if not vendors:
        print("No vendor users found. Skipping dummy order creation.")
        return

    customers = await User.filter(is_vendor=False).all()
    if not customers:
        customers = await User.all().all()
    if not customers:
        print("No users found for customer assignment. Skipping dummy order creation.")
        return

    total_created = 0

    for vendor in vendors:
        existing_total_count = await Order.filter(vendor_id=vendor.id).count()
        existing_dummy_count = await Order.filter(
            vendor_id=vendor.id,
            id__startswith="DUMMY-",
        ).count()
        needed = max(0, per_vendor - existing_dummy_count)

        vendor_items = list(await Item.filter(vendor_id=vendor.id).limit(200))
        if not vendor_items:
            vendor_items = [await _ensure_vendor_has_item(vendor)]

        created_for_vendor = 0
        for _ in range(needed):
            customer = random.choice(customers)
            max_items = min(3, len(vendor_items))
            item_count = random.randint(1, max_items) if max_items > 0 else 1
            chosen_items = random.sample(vendor_items, k=item_count)

            subtotal = Decimal("0.00")
            item_rows = []
            for item in chosen_items:
                base_price = Decimal(str(item.price))
                discount_pct = Decimal(str(item.discount or 0))
                unit_price = _money(base_price - (base_price * discount_pct / Decimal("100")))
                quantity = random.randint(1, 3)
                subtotal += unit_price * quantity
                item_rows.append(
                    {
                        "item_id": item.id,
                        "title": item.title,
                        "price": unit_price,
                        "quantity": quantity,
                        "image_path": item.image or "",
                    }
                )

            subtotal = _money(subtotal)
            delivery_fee = _money(Decimal(str(random.choice([0, 20, 30, 40]))))
            discount = _money(Decimal(str(random.choice([0, 5, 10]))))
            total = _money(max(Decimal("0.00"), subtotal + delivery_fee - discount))

            order_id = f"DUMMY-{vendor.id}-{uuid4().hex[:12]}"
            completed_at = datetime.now(timezone.utc) - timedelta(days=random.randint(8, 30))

            order = await Order.create(
                id=order_id,
                parent_order_id=order_id,
                user_id=customer.id,
                vendor_id=vendor.id,
                delivery_type=DeliveryTypeEnum.COMBINED,
                payment_method=PaymentMethodType.COD,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total=total,
                discount=discount,
                status=OrderStatus.DELIVERED,
                payment_status="paid",
                transaction_id=f"TXN-{uuid4().hex[:10]}",
                tracking_number=f"TRK-{uuid4().hex[:10]}",
                completed_at=completed_at,
                metadata={"is_dummy": True},
            )
            await _apply_last_3_weeks_timestamps(order.id)

            for row in item_rows:
                await OrderItem.create(
                    order_id=order.id,
                    item_id=row["item_id"],
                    title=row["title"],
                    price=str(row["price"]),
                    quantity=row["quantity"],
                    image_path=row["image_path"],
                )

            total_created += 1
            created_for_vendor += 1

        # Ensure timestamps are spread for existing dummy orders as well.
        existing_dummy_orders = await Order.filter(
            vendor_id=vendor.id,
            id__startswith="DUMMY-",
        ).all()
        for order in existing_dummy_orders:
            await _apply_last_3_weeks_timestamps(order.id)

        print(
            f"Vendor {vendor.id}: created={created_for_vendor}, "
            f"existing_total={existing_total_count}, existing_dummy={existing_dummy_count}, "
            f"target={per_vendor}, "
            f"timestamp_updated={len(existing_dummy_orders)}"
        )

    print(f"Dummy order generation completed. Total created: {total_created}")
