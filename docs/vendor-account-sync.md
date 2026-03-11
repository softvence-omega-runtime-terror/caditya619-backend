# Vendor Account `/sync` Endpoint

## Endpoint
- Method: `POST`
- Path: `/earning/vendor/vendor_account/orders/{order_id}/sync`
- Auth: vendor token (`vendor_required`)


## What it does
This endpoint does a full vendor-account recalculation for the vendor attached to `order_id`.

It does not "add a fixed amount". Instead, it recomputes balances from source tables:
- `orders` (delivered earnings)
- `payouttransaction` (successful withdrawals)


## When to use
- Right after a business event where vendor balances should be refreshed immediately (for example, order delivered, manual data correction, admin reconciliation).
- When you need fresh `available_for_withdraw` without waiting for scheduled sync.


## Validation flow
1. Verify the order belongs to the logged-in vendor.
2. Load `order.vendor -> vendor_profile`.
3. Get/create `VendorAccount`.
4. Run `refresh_balances(reference_time=now_utc)`.
5. Return synchronized totals.


## Calculation logic
All money values are rounded to 2 decimals (`Decimal`, half-up).

```text
commission_percent = clamp(vendor.commission, 0, 100)

gross_total = SUM(order.total)
  WHERE order.vendor_id = vendor_user_id
    AND order.status = 'delivered'

commission_amount = gross_total * commission_percent / 100
total_earnings = max(0, gross_total - commission_amount)

matured_earnings = net earnings from delivered orders older than 7 days
total_withdrawn = SUM(payout.amount)
  WHERE payout.vendor_id = vendor_profile_id
    AND payout.status = 'success'

available_for_withdraw = max(0, matured_earnings - total_withdrawn)

release_window_earnings = net earnings from delivered orders:
  [reference_time - 14 days, reference_time - 7 days)
```

Delivered-date source:
- Primary: `orders.completed_at`
- Fallback: `orders.order_date` when `completed_at` is null


## Example
Given:
- `gross_total = 10000.00`
- `commission_percent = 12`
- `matured_earnings = 6000.00`
- `total_withdrawn = 1500.00`

Then:
- `commission_amount = 1200.00`
- `total_earnings = 8800.00`
- `available_for_withdraw = 4500.00`


## Response shape
```json
{
  "success": true,
  "order_id": "ORD123",
  "vendor_user_id": 77,
  "vendor_profile_id": 12,
  "total_earnings": "8800.00",
  "matured_earnings": "6000.00",
  "total_withdrawn": "1500.00",
  "available_for_withdraw": "4500.00",
  "release_window_earnings": "2200.00",
  "synced_at": "2026-03-11T12:00:00+00:00"
}
```


## Backward compatibility
Legacy endpoints still call the same sync logic:
- `POST /earning/vendor/vendor_account/orders/{order_id}/credit` (deprecated)
- `POST /earning/vendor/vendor_account/orders/{order_id}/refund` (deprecated)
