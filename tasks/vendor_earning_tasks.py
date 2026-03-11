import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from app.task_config import run_async_task
from app.utils.task_decorators import every
from applications.earning.vendor_earning import (
    AutoPayoutStatus,
    Beneficiary,
    PayoutStatus,
    PayoutTransaction,
    get_or_create_vendor_account,
)
from applications.user.vendor import VendorProfile
from routes.earning.vendor_earn import withdraw_amount

logger = logging.getLogger(__name__)
MONEY_QUANTIZER = Decimal("0.01")
ZERO_DECIMAL = Decimal("0.00")
AUTO_TRANSFER_PREFIX = "AUTO"


def _to_money(value) -> Decimal:
    if value is None:
        return ZERO_DECIMAL
    return Decimal(str(value)).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _auto_period_start(reference_time: datetime, status: AutoPayoutStatus) -> datetime:
    if status == AutoPayoutStatus.WEEKLY:
        # Monday (00:00 UTC) of current week
        return (reference_time - timedelta(days=reference_time.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if status == AutoPayoutStatus.MONTHLY:
        return reference_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if status == AutoPayoutStatus.YEARLY:
        return reference_time.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return reference_time


def _build_transfer_id(beneficiary: Beneficiary, status: AutoPayoutStatus) -> str:
    return (
        f"{AUTO_TRANSFER_PREFIX}-{status.value.upper()}-"
        f"V{beneficiary.vendor_id}-B{beneficiary.id}-{int(time.time())}"
    )

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
        run_async_task(_task())
    except Exception as exc:
        logger.error("Vendor earning weekly sync failed: %s", str(exc))


@every(hour=1, minute=15)
def run_vendor_auto_payouts():
    """
    Daily task:
    - weekly/monthly/yearly auto-payout evaluation from Beneficiary settings
    - payout only when vendor has enough available_for_withdraw
    - create PayoutTransaction row for each attempt
    """

    async def _task():
        reference_time = datetime.now(timezone.utc)
        beneficiaries = await Beneficiary.filter(is_active=True).all()

        scanned_count = 0
        attempted_count = 0
        paid_count = 0
        skipped_count = 0
        failed_count = 0

        for beneficiary in beneficiaries:
            scanned_count += 1
            try:
                raw_status = beneficiary.auto_payout_status
                if isinstance(raw_status, AutoPayoutStatus):
                    auto_status = raw_status
                else:
                    auto_status = AutoPayoutStatus(str(raw_status))

                if auto_status == AutoPayoutStatus.MANUAL:
                    skipped_count += 1
                    continue

                if not beneficiary.beneficiary_id or not beneficiary.email or not beneficiary.phone:
                    skipped_count += 1
                    logger.warning(
                        "Skipping auto payout. Missing beneficiary contact details for beneficiary=%s vendor=%s",
                        beneficiary.id,
                        beneficiary.vendor_id,
                    )
                    continue

                configured_amount = _to_money(beneficiary.auto_payout_amount)
                if configured_amount <= ZERO_DECIMAL:
                    skipped_count += 1
                    continue

                period_start = _auto_period_start(reference_time, auto_status)
                already_paid_for_period = await PayoutTransaction.filter(
                    vendor_id=beneficiary.vendor_id,
                    beneficiary_id=beneficiary.id,
                    status=PayoutStatus.SUCCESS.value,
                    transfer_id__startswith=f"{AUTO_TRANSFER_PREFIX}-",
                    created_at__gte=period_start,
                ).exists()
                if already_paid_for_period:
                    skipped_count += 1
                    continue

                vendor_profile = await VendorProfile.get_or_none(id=beneficiary.vendor_id)
                if not vendor_profile:
                    skipped_count += 1
                    logger.warning(
                        "Skipping auto payout. Vendor profile missing for vendor=%s",
                        beneficiary.vendor_id,
                    )
                    continue

                vendor_account = await get_or_create_vendor_account(vendor_profile)
                await vendor_account.refresh_balances(reference_time=reference_time)
                available_for_withdraw = _to_money(vendor_account.available_for_withdraw)
                if available_for_withdraw < configured_amount:
                    skipped_count += 1
                    continue

                attempted_count += 1
                transfer_id = _build_transfer_id(beneficiary, auto_status)
                await vendor_profile.fetch_related("user")
                vendor_user = vendor_profile.user

                try:
                    response_payload = await withdraw_amount(
                        amount=int(configured_amount),
                        vendor=vendor_user,
                    )

                    raw_status = str(response_payload.get("status", PayoutStatus.SUCCESS.value)).lower()
                    normalized_status = (
                        raw_status if raw_status in {s.value for s in PayoutStatus} else PayoutStatus.SUCCESS.value
                    )

                    await PayoutTransaction.create(
                        vendor_id=beneficiary.vendor_id,
                        beneficiary_id=beneficiary.id,
                        transfer_id=transfer_id,
                        amount=configured_amount,
                        status=normalized_status,
                        cf_response={
                            "source": "auto_payout_task",
                            "auto_payout_status": auto_status.value,
                            "cashfree": response_payload,
                        },
                    )
                    await vendor_account.refresh_balances(reference_time=reference_time)

                    if normalized_status == PayoutStatus.FAILED.value:
                        failed_count += 1
                    else:
                        paid_count += 1

                except HTTPException as exc:
                    failed_count += 1
                    await PayoutTransaction.create(
                        vendor_id=beneficiary.vendor_id,
                        beneficiary_id=beneficiary.id,
                        transfer_id=transfer_id,
                        amount=configured_amount,
                        status=PayoutStatus.FAILED.value,
                        cf_response={
                            "source": "auto_payout_task",
                            "auto_payout_status": auto_status.value,
                            "http_status": exc.status_code,
                            "detail": exc.detail,
                        },
                    )

            except ValueError:
                # Handles invalid enum values in persisted rows.
                skipped_count += 1
                logger.warning(
                    "Skipping auto payout. Invalid auto_payout_status for beneficiary=%s",
                    beneficiary.id,
                )
            except Exception as exc:
                failed_count += 1
                logger.error(
                    "Auto payout task failed for beneficiary=%s vendor=%s: %s",
                    beneficiary.id,
                    beneficiary.vendor_id,
                    str(exc),
                )

        logger.info(
            "Vendor auto payout run completed. scanned=%s attempted=%s paid=%s skipped=%s failed=%s at=%s",
            scanned_count,
            attempted_count,
            paid_count,
            skipped_count,
            failed_count,
            reference_time.isoformat(),
        )

    try:
        run_async_task(_task())
    except Exception as exc:
        logger.error("Vendor auto payout run failed: %s", str(exc))
