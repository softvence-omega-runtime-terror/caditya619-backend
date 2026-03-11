import asyncio
import logging
import time
from collections import defaultdict
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
SYNC_VENDOR_CONCURRENCY = 8
AUTO_PAYOUT_VENDOR_CONCURRENCY = 4
VALID_PAYOUT_STATUSES = {status.value for status in PayoutStatus}
AUTO_SUCCESS_STATUS = PayoutStatus.SUCCESS.value
AUTO_FAILED_STATUS = PayoutStatus.FAILED.value


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


# @every(seconds=10)
@every(day_of_week="mon", hour=1, minute=1)
def sync_vendor_withdrawable_balances_weekly():
    async def _task():
        reference_time = datetime.now(timezone.utc)
        vendors = await VendorProfile.all().only("id")
        if not vendors:
            logger.info(
                "Vendor earning sync completed. updated=0 reference_time=%s",
                reference_time.isoformat(),
            )
            return

        semaphore = asyncio.Semaphore(SYNC_VENDOR_CONCURRENCY)

        async def _sync_vendor(vendor):
            async with semaphore:
                try:
                    vendor_account = await get_or_create_vendor_account(vendor)
                    await vendor_account.refresh_balances(
                        reference_time=reference_time,
                        force_save=False,
                        sync_touch_interval_seconds=3600,
                    )
                    return True
                except Exception as exc:
                    logger.error(
                        "Failed to sync vendor earning for vendor_id=%s: %s",
                        vendor.id,
                        str(exc),
                    )
                    return False

        results = await asyncio.gather(*[_sync_vendor(vendor) for vendor in vendors])
        updated_count = sum(1 for result in results if result)

        logger.info(
            "Vendor earning sync completed. updated=%s reference_time=%s",
            updated_count,
            reference_time.isoformat(),
        )

    try:
        run_async_task(_task())
    except Exception as exc:
        logger.error("Vendor earning sync failed: %s", str(exc))


# @every(seconds=10)
@every(hour=1, minute=15)
def run_vendor_auto_payouts():
    async def _task():
        reference_time = datetime.now(timezone.utc)
        beneficiaries = (
            await Beneficiary.filter(is_active=True)
            .only(
                "id",
                "vendor_id",
                "beneficiary_id",
                "email",
                "phone",
                "auto_payout_amount",
                "auto_payout_status",
            )
            .all()
        )

        scanned_count = len(beneficiaries)
        attempted_count = 0
        paid_count = 0
        skipped_count = 0
        failed_count = 0

        if not beneficiaries:
            logger.info(
                "Vendor auto payout run completed. scanned=0 attempted=0 paid=0 skipped=0 failed=0 at=%s",
                reference_time.isoformat(),
            )
            return

        candidate_items = []
        beneficiary_ids_by_status = {
            AutoPayoutStatus.WEEKLY: [],
            AutoPayoutStatus.MONTHLY: [],
            AutoPayoutStatus.YEARLY: [],
        }

        for beneficiary in beneficiaries:
            try:
                raw_status = beneficiary.auto_payout_status
                auto_status = (
                    raw_status if isinstance(raw_status, AutoPayoutStatus) else AutoPayoutStatus(str(raw_status))
                )
            except ValueError:
                skipped_count += 1
                logger.warning(
                    "Skipping auto payout. Invalid auto_payout_status for beneficiary=%s",
                    beneficiary.id,
                )
                continue

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

            candidate_items.append((beneficiary, auto_status, configured_amount))
            beneficiary_ids_by_status[auto_status].append(beneficiary.id)

        if not candidate_items:
            logger.info(
                "Vendor auto payout run completed. scanned=%s attempted=0 paid=0 skipped=%s failed=0 at=%s",
                scanned_count,
                skipped_count,
                reference_time.isoformat(),
            )
            return

        period_start_by_status = {
            AutoPayoutStatus.WEEKLY: _auto_period_start(reference_time, AutoPayoutStatus.WEEKLY),
            AutoPayoutStatus.MONTHLY: _auto_period_start(reference_time, AutoPayoutStatus.MONTHLY),
            AutoPayoutStatus.YEARLY: _auto_period_start(reference_time, AutoPayoutStatus.YEARLY),
        }

        async def _already_paid_ids_for(status: AutoPayoutStatus):
            ids = beneficiary_ids_by_status[status]
            if not ids:
                return set()
            paid_ids = await PayoutTransaction.filter(
                beneficiary_id__in=ids,
                status=AUTO_SUCCESS_STATUS,
                transfer_id__startswith=f"{AUTO_TRANSFER_PREFIX}-",
                created_at__gte=period_start_by_status[status],
            ).values_list("beneficiary_id", flat=True)
            return set(paid_ids)

        weekly_paid, monthly_paid, yearly_paid = await asyncio.gather(
            _already_paid_ids_for(AutoPayoutStatus.WEEKLY),
            _already_paid_ids_for(AutoPayoutStatus.MONTHLY),
            _already_paid_ids_for(AutoPayoutStatus.YEARLY),
        )
        already_paid_by_status = {
            AutoPayoutStatus.WEEKLY: weekly_paid,
            AutoPayoutStatus.MONTHLY: monthly_paid,
            AutoPayoutStatus.YEARLY: yearly_paid,
        }

        due_items = []
        for beneficiary, auto_status, configured_amount in candidate_items:
            if beneficiary.id in already_paid_by_status[auto_status]:
                skipped_count += 1
                continue
            due_items.append((beneficiary, auto_status, configured_amount))

        if not due_items:
            logger.info(
                "Vendor auto payout run completed. scanned=%s attempted=0 paid=0 skipped=%s failed=0 at=%s",
                scanned_count,
                skipped_count,
                reference_time.isoformat(),
            )
            return

        vendor_ids = sorted({beneficiary.vendor_id for beneficiary, _, _ in due_items})
        vendor_profiles = await VendorProfile.filter(id__in=vendor_ids).prefetch_related("user")
        profiles_by_vendor_id = {vendor_profile.id: vendor_profile for vendor_profile in vendor_profiles}

        due_items_by_vendor_id = defaultdict(list)
        for item in due_items:
            beneficiary, _, _ = item
            if beneficiary.vendor_id not in profiles_by_vendor_id:
                skipped_count += 1
                logger.warning(
                    "Skipping auto payout. Vendor profile missing for vendor=%s",
                    beneficiary.vendor_id,
                )
                continue
            due_items_by_vendor_id[beneficiary.vendor_id].append(item)

        if not due_items_by_vendor_id:
            logger.info(
                "Vendor auto payout run completed. scanned=%s attempted=0 paid=0 skipped=%s failed=0 at=%s",
                scanned_count,
                skipped_count,
                reference_time.isoformat(),
            )
            return

        vendor_accounts_by_id = {}
        available_balance_by_vendor_id = {}
        prepare_semaphore = asyncio.Semaphore(SYNC_VENDOR_CONCURRENCY)

        async def _prepare_vendor(vendor_id):
            async with prepare_semaphore:
                try:
                    vendor_profile = profiles_by_vendor_id[vendor_id]
                    vendor_account = await get_or_create_vendor_account(vendor_profile)
                    await vendor_account.refresh_balances(
                        reference_time=reference_time,
                        force_save=False,
                        sync_touch_interval_seconds=3600,
                    )
                    return vendor_id, vendor_account, _to_money(vendor_account.available_for_withdraw), None
                except Exception as exc:
                    return vendor_id, None, ZERO_DECIMAL, exc

        prepare_results = await asyncio.gather(
            *[_prepare_vendor(vendor_id) for vendor_id in due_items_by_vendor_id.keys()]
        )

        for vendor_id, vendor_account, available_balance, error in prepare_results:
            if error is not None:
                failed_count += len(due_items_by_vendor_id[vendor_id])
                logger.error(
                    "Auto payout prep failed for vendor=%s: %s",
                    vendor_id,
                    str(error),
                )
                continue
            vendor_accounts_by_id[vendor_id] = vendor_account
            available_balance_by_vendor_id[vendor_id] = available_balance

        process_vendor_ids = [
            vendor_id for vendor_id in due_items_by_vendor_id.keys() if vendor_id in vendor_accounts_by_id
        ]
        if not process_vendor_ids:
            logger.info(
                "Vendor auto payout run completed. scanned=%s attempted=0 paid=0 skipped=%s failed=%s at=%s",
                scanned_count,
                skipped_count,
                failed_count,
                reference_time.isoformat(),
            )
            return

        process_semaphore = asyncio.Semaphore(AUTO_PAYOUT_VENDOR_CONCURRENCY)

        async def _process_vendor(vendor_id):
            async with process_semaphore:
                vendor_profile = profiles_by_vendor_id[vendor_id]
                vendor_user = vendor_profile.user
                try:
                    vendor_user.vendor_profile = vendor_profile
                except Exception:
                    # Relation assignment is a best-effort cache optimization.
                    pass
                vendor_account = vendor_accounts_by_id[vendor_id]
                available_balance = available_balance_by_vendor_id[vendor_id]

                local_attempted = 0
                local_paid = 0
                local_skipped = 0
                local_failed = 0
                touched = False

                for beneficiary, auto_status, configured_amount in due_items_by_vendor_id[vendor_id]:
                    if available_balance < configured_amount:
                        local_skipped += 1
                        continue

                    local_attempted += 1
                    touched = True
                    transfer_id = _build_transfer_id(beneficiary, auto_status)

                    try:
                        response_payload = await withdraw_amount(
                            amount=int(configured_amount),
                            vendor=vendor_user,
                            transfer_id=transfer_id,
                        )

                        raw_status = str(response_payload.get("status", AUTO_SUCCESS_STATUS)).lower()
                        normalized_status = (
                            raw_status if raw_status in VALID_PAYOUT_STATUSES else AUTO_SUCCESS_STATUS
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

                        if normalized_status == AUTO_FAILED_STATUS:
                            local_failed += 1
                        else:
                            local_paid += 1
                            available_balance = _to_money(available_balance - configured_amount)

                    except HTTPException as exc:
                        local_failed += 1
                        await PayoutTransaction.create(
                            vendor_id=beneficiary.vendor_id,
                            beneficiary_id=beneficiary.id,
                            transfer_id=transfer_id,
                            amount=configured_amount,
                            status=AUTO_FAILED_STATUS,
                            cf_response={
                                "source": "auto_payout_task",
                                "auto_payout_status": auto_status.value,
                                "http_status": exc.status_code,
                                "detail": exc.detail,
                            },
                        )
                    except Exception as exc:
                        local_failed += 1
                        logger.error(
                            "Auto payout failed for beneficiary=%s vendor=%s: %s",
                            beneficiary.id,
                            beneficiary.vendor_id,
                            str(exc),
                        )
                        await PayoutTransaction.create(
                            vendor_id=beneficiary.vendor_id,
                            beneficiary_id=beneficiary.id,
                            transfer_id=transfer_id,
                            amount=configured_amount,
                            status=AUTO_FAILED_STATUS,
                            cf_response={
                                "source": "auto_payout_task",
                                "auto_payout_status": auto_status.value,
                                "detail": str(exc),
                            },
                        )

                if touched:
                    try:
                        await vendor_account.refresh_balances(
                            reference_time=reference_time,
                            force_save=True,
                            sync_touch_interval_seconds=0,
                        )
                    except Exception as exc:
                        logger.error(
                            "Auto payout post-refresh failed for vendor=%s: %s",
                            vendor_id,
                            str(exc),
                        )

                return local_attempted, local_paid, local_skipped, local_failed

        process_results = await asyncio.gather(
            *[_process_vendor(vendor_id) for vendor_id in process_vendor_ids]
        )
        for local_attempted, local_paid, local_skipped, local_failed in process_results:
            attempted_count += local_attempted
            paid_count += local_paid
            skipped_count += local_skipped
            failed_count += local_failed

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
