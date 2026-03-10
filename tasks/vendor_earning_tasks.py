import asyncio
import logging
from datetime import datetime, timezone

from app.utils.task_decorators import every
from applications.earning.vendor_earning import VendorEarning
from applications.user.vendor import VendorProfile

logger = logging.getLogger(__name__)


@every(day_of_week="mon", hour=1, minute=0)
def sync_vendor_withdrawable_balances_weekly():
    """
    Weekly earning sync:
    - total earnings: all delivered orders
    - available_for_withdraw: matured delivered orders (older than 7 days), minus withdrawn
    """

    async def _task():
        reference_time = datetime.now(timezone.utc)
        vendors = await VendorProfile.all().only("id")
        updated_count = 0

        for vendor in vendors:
            try:
                vendor_earning, _ = await VendorEarning.get_or_create(vendor_id=vendor.id)
                await vendor_earning.refresh_balances(reference_time=reference_time)
                updated_count += 1
            except Exception as exc:
                logger.error(
                    "Failed to sync vendor earning for vendor_id=%s: %s",
                    vendor.id,
                    str(exc),
                )

        logger.info(
            "Vendor earning weekly sync completed. updated=%s reference_time=%s",
            updated_count,
            reference_time.isoformat(),
        )

    try:
        asyncio.run(_task())
    except Exception as exc:
        logger.error("Vendor earning weekly sync failed: %s", str(exc))
