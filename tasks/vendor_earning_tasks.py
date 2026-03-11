import asyncio
import logging
from datetime import datetime, timezone

from app.utils.task_decorators import every
from applications.earning.vendor_earning import VendorAccount, get_or_create_vendor_account
from applications.user.vendor import VendorProfile

logger = logging.getLogger(__name__)

# day_of_week="mon", hour=1, 
@every(minute=1)
def sync_vendor_withdrawable_balances_weekly():
    text = """
    Weekly earning sync:
    - total_earnings: all delivered order totals minus vendor commission
    - available_for_withdraw: matured earnings (orders older than 7 days), minus withdrawn
    """
    print(text)

    async def _task():
        reference_time = datetime.now(timezone.utc)
        vendors = await VendorProfile.all().only("id")
        updated_count = 0

        for vendor in vendors:
            try:
                vendor_account = await get_or_create_vendor_account(vendor)
                await vendor_account.refresh_balances(reference_time=reference_time)
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
