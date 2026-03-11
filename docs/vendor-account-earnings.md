# Vendor Account Earnings Docs

## Scope
This document explains how vendor earning/account calculation works in this project.

Code references:
- Model and calculation logic: `applications/earning/vendor_earning.py`
- API routes: `routes/earning/vendor_earn.py`
- Background sync task: `tasks/vendor_earning_tasks.py`


## Data Model
`VendorAccount` fields:
- `vendor`: one-to-one with `VendorProfile`
- `total_earnings`: net delivered earnings after commission
- `total_withdrow`: sum of successful payouts (field name kept as-is in code)
- `available_for_withdraw`: matured net earnings (older than 7 days) minus withdrawals
- `last_withdrawable_sync_at`: last sync time used for withdrawable calculation
- `updated_at`: auto-updated on save

Related models:
- `Order`: source of delivered revenue (`Order.total`)
- `PayoutTransaction`: source of withdrawals (`amount` where status is `success`)


## Core Formulas
The system uses these formulas:

```text
gross_total = sum(delivered order.total)
commission = gross_total * vendor.commission / 100
net_total = max(0, gross_total - commission)

total_withdrow = sum(payout.amount where payout.status == success)

matured_net = net earnings from delivered orders older than 7 days
available_for_withdraw = max(0, matured_net - total_withdrow)

pending_balance = total_earnings - total_withdrow
```

All amounts are rounded to 2 decimals with Decimal quantization.


## Date Rules (7-day Hold)
Delivered orders are split into windows:

- Last 7 days: **not withdrawable** (refund safety window)
- Older than 7 days: withdrawable candidate
- Release window metric: 14 days ago (inclusive) to 7 days ago (exclusive)

Date filtering uses:
- `completed_at` when available
- fallback to `order_date` for legacy rows where `completed_at` is null


## Balance Refresh Lifecycle
### 1) On API read (`GET /vendor_account`)
Route behavior:
- Load vendor profile and vendor account
- If `last_withdrawable_sync_at` is missing or older than 7 days, run `refresh_balances()`
- Return period summary + stored account balances

### 2) Scheduled sync task
Task iterates all vendor profiles and runs `refresh_balances(reference_time=now)`.

Current decorator in code:
- `@every(minute=1)` (runs every minute)

If you want true weekly release behavior, switch back to weekly schedule in task decorator.


## Auto-Recovery for Missing Table
If MySQL raises:
- `OperationalError (1146): table vendoraccount doesn't exist`

The helper `get_or_create_vendor_account()` handles it by:
1. checking existence once
2. auto-running `Tortoise.generate_schemas(safe=True)` when missing
3. continuing normal get/create flow

This prevents the endpoint/task from crashing due to missing `vendoraccount`.


## API Endpoints
Base path (mounted): `/earning/vendor`

### `GET /earning/vendor/vendor_account`
Query:
- `period` (optional): `this_month`, `this_week`, `this_year`

Response:
- `vendor_id`
- `total_earnings`
- `average_earnings`
- `total_orders`
- `total_withdraw`
- `total_pending`
- `available_for_withdraw`
- `pending_balance`
- `updated_at`

### `POST /earning/vendor/vendor_account/orders/{order_id}/credit`
Purpose:
- Recalculate vendor account after a credit-worthy order event.

### `POST /earning/vendor/vendor_account/orders/{order_id}/refund`
Purpose:
- Recalculate vendor account after a refund-worthy order event.

### `POST /earning/vendor/add_beneficiary`
Purpose:
- Add payout beneficiary bank details.

### `POST /earning/vendor/transfer`
Purpose:
- Request transfer to beneficiary account.


## Example Interpretation
Example response:

```json
{
  "vendor_id": 4,
  "total_earnings": 5720.65,
  "average_earnings": 286.03,
  "total_orders": 20,
  "total_withdraw": 0,
  "total_pending": 5720.65,
  "available_for_withdraw": 3774.33,
  "pending_balance": 5720.65,
  "updated_at": "2026-03-11T16:11:33.994242+06:00"
}
```

Interpretation:
- `total_earnings` is net over all delivered orders
- `total_withdraw` is 0, so `pending_balance == total_earnings`
- `available_for_withdraw` is lower than `total_earnings` because last 7-day orders are held
- Hold amount = `total_earnings - available_for_withdraw = 1946.32`


## Notes / Known Constraints
- Field name is intentionally `total_withdrow` in DB/model for compatibility.
- `available_for_withdraw` is stored and updated on refresh cycles; it is not recomputed on every DB read.
- Payout totals only include `PayoutTransaction` rows with status `success`.

