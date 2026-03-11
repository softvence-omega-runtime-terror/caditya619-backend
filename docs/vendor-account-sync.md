# Vendor Account Sync Now

## Endpoint
- Method: `POST`
- Path: `/earning/vendor/vendor_account/sync_now`
- Auth: vendor token (`vendor_required`)


## Purpose
Force recalculation of vendor account balances immediately, without waiting for the scheduled task.


## What gets recalculated
- `total_earnings`
- `total_withdrow`
- `available_for_withdraw`
- `last_withdrawable_sync_at`


## Calculation
```text
gross_total = SUM(order.total)
  WHERE order.vendor_id = vendor_user_id
    AND order.status = 'delivered'

commission_amount = gross_total * vendor.commission / 100
total_earnings = max(0, gross_total - commission_amount)

total_withdrow = SUM(payout.amount)
  WHERE payout.vendor_id = vendor_profile_id
    AND payout.status = 'success'

matured_earnings = net delivered earnings older than 7 days
available_for_withdraw = max(0, matured_earnings - total_withdrow)
```

Date source for delivered window:
- Use `completed_at` when present
- Fallback to `order_date` when `completed_at` is null


## Response fields
- `success`
- `vendor_id`
- `total_earnings`
- `matured_earnings`
- `release_window_earnings`
- `total_withdrawn`
- `available_for_withdraw`
- `synced_at`
- `updated_at`
