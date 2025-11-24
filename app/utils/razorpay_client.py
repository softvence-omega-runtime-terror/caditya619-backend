# # utils/razorpay_client.py
# import razorpayX
# #from decouple import config  # or use os.environ
# from applications.user.models import User

# # Your Test Keys (replace with live keys later)
# RAZORPAY_X_KEY = "rzp_test_RjQKo4DwGUWRL2"
# RAZORPAY_X_SECRET = "jAz4I7qRwSYX9UyFrZIoxdGs"

# client = razorpayX.Client(auth=(RAZORPAY_X_KEY, RAZORPAY_X_SECRET))



# # Create or get contact & fund account for rider
# def get_or_create_fund_account(rider):
#     print("Razorpay client initialized.", client.customer)
#     for cl in client.__dir__():
#         print("Client has attribute:", cl)

#     #user = User.get(id=rider.user.id)
#     # Search existing contact
    
#     #contacts = client.contact.all({"name": rider.user.full_name or "Rider"})
#     contacts = client.contact.all({"reference_id": str(rider.id)})
#     print("Contacts found:", contacts)
#     contact = contacts["items"][0] if contacts["items"] else None

#     print("Getting/creating fund account for rider:", rider.id)

#     if not contact:
#         contact = client.contact.create({
#             "name": rider.user.full_name or "Rider",
#             "email": rider.user.email or f"rider{rider.id}@example.com",
#             "contact": rider.user.phone or "9999999999",
#             "type": "employee",
#             "reference_id": str(rider.id),
#         })

#     # Check if fund account exists
#     fund_accounts = client.fund_account.all({"contact_id": contact["id"]})
#     fund_account = fund_accounts["items"][0] if fund_accounts["22items"] else None

#     if not fund_account:
#         fund_account = client.fund_account.create({
#             "contact_id": contact["id"],
#             "account_type": "bank_account",
#             "bank_account": {
#                 "name": rider.user.full_name,
#                 "account_number": rider.bank_account_number,      # You must add this field
#                 "ifsc": rider.bank_ifsc,                           # Add this too
#             }
#         })

#     return fund_account




# utils/razorpay_client.py
# import razorpay
# import requests
# from requests.auth import HTTPBasicAuth
# from typing import Optional

# # Your Test Keys (replace with live keys later)
# RAZORPAY_KEY = "rzp_test_RikzhWRtsuGWEM"
# RAZORPAY_SECRET = "VoXXEQvndf0lV16AJB2j6GWU"
# RAZORPAY_BASE = "https://api.razorpay.com/v1"

# client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))


# def _http_get(path: str, params: Optional[dict] = None):
#     url = f"{RAZORPAY_BASE}{path}"
#     resp = requests.get(url, auth=HTTPBasicAuth(RAZORPAY_KEY, RAZORPAY_SECRET), params=params or {})
#     resp.raise_for_status()
#     return resp.json()


# def _http_post(path: str, payload: dict):
#     url = f"{RAZORPAY_BASE}{path}"
#     resp = requests.post(url, json=payload, auth=HTTPBasicAuth(RAZORPAY_KEY, RAZORPAY_SECRET))
#     resp.raise_for_status()
#     return resp.json()


# def get_or_create_fund_account(rider):
#     """
#     Returns a Razorpay fund_account dict for the given `rider`.
#     Works with razorpay SDK if it exposes contact/fund_account resources,
#     otherwise falls back to direct HTTP calls to Razorpay endpoints.
#     """

    
#     # safe attribute access
#     user = getattr(rider, "user", None)
#     full_name = getattr(user, "full_name", None) or getattr(user, "name", None) or f"Rider {getattr(rider, 'id', '')}"
#     email = getattr(user, "email", None) or f"rider{getattr(rider, 'id', '')}@example.com"
#     phone = getattr(user, "phone", None) or getattr(user, "contact", None) or "9999999999"

#     acct = getattr(rider, "bank_account_number", None)
#     ifsc = getattr(rider, "bank_ifsc", None)
#     if not acct or not ifsc:
#         raise ValueError("Rider must have bank_account_number and bank_ifsc set before creating fund account")

#     # Try using SDK resources if available
#     contact = None
#     try:
        
#         if hasattr(client, "contact") and hasattr(client, "fund_account"):
#             # attempt to search contacts via SDK
#             print("Getting/creating fund account for rider:", rider.id)
#             try:
#                 contacts = client.contact.all({"name": full_name}) or {}
#                 items = contacts.get("items", []) if isinstance(contacts, dict) else contacts
#                 contact = items[0] if items else None
#             except Exception:
#                 # some SDK versions or environments might not support .contact.* — fall back
#                 contact = None

#             # create contact if not found
#             if not contact:
#                 contact = client.contact.create({
#                     "name": full_name,
#                     "email": email,
#                     "contact": phone,
#                     "type": "employee",
#                     "reference_id": str(getattr(rider, "id", "")),
#                 })

#             # check fund accounts (fixed the "22items" typo)
#             try:
#                 fund_accounts = client.fund_account.all({"contact_id": contact["id"]}) or {}
#                 fa_items = fund_accounts.get("items", []) if isinstance(fund_accounts, dict) else fund_accounts
#             except Exception:
#                 fa_items = []

#             fund_account = None
#             for fa in fa_items:
#                 bank_account = fa.get("bank_account") or {}
#                 if bank_account.get("account_number") == acct:
#                     fund_account = fa
#                     break

#             if not fund_account:
#                 fund_account = client.fund_account.create({
#                     "contact_id": contact["id"],
#                     "account_type": "bank_account",
#                     "bank_account": {
#                         "name": full_name,
#                         "account_number": acct,
#                         "ifsc": ifsc,
#                     }
#                 })

#             return fund_account
#         else:
#             # SDK missing contact/fund_account resources -> fall through to HTTP fallback
#             raise AttributeError("razorpay.Client missing contact/fund_account")
#     except AttributeError:
#         # HTTP fallback below
#         pass
#     except Exception as e:
#         # If SDK call failed for unexpected reason, fall back to HTTP approach as well
#         # (but don't swallow the error if you prefer to fail fast: you can re-raise)
#         # print or log if you have a logger; for now we just fall back
#         pass

#     # ---------- HTTP fallback (uses requests, same keys above) ----------
#     # 1) Try to find contact by reference_id OR by email/phone/name
#     try:
#         resp = _http_get("/contacts", params={"q": full_name})
#         items = resp.get("items", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
#         contact = None
#         for c in items:
#             if str(c.get("reference_id")) == str(getattr(rider, "id", "")):
#                 contact = c
#                 break
#             if c.get("email") == email or c.get("contact") == phone or c.get("name") == full_name:
#                 contact = c
#                 break
#     except Exception:
#         contact = None

#     if not contact:
#         contact_payload = {
#             "name": full_name,
#             "email": email,
#             "contact": phone,
#             "type": "employee",
#             "reference_id": str(getattr(rider, "id", "")),
#         }
#         contact = _http_post("/contacts", contact_payload)

#     contact_id = contact["id"]

#     # 2) Check fund accounts for this contact
#     try:
#         resp = _http_get("/fund_accounts", params={"contact_id": contact_id})
#         fa_items = resp.get("items", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
#     except Exception:
#         fa_items = []

#     fund_account = None
#     for fa in fa_items:
#         bank_account = fa.get("bank_account") or {}
#         if bank_account.get("account_number") == acct:
#             fund_account = fa
#             break

#     if not fund_account:
#         create_payload = {
#             "contact_id": contact_id,
#             "account_type": "bank_account",
#             "bank_account": {
#                 "name": full_name,
#                 "ifsc": ifsc,
#                 "account_number": acct,
#             }
#         }
#         fund_account = _http_post("/fund_accounts", create_payload)

#     return fund_account








# utils/razorpay_payout.py
# utils/razorpay_x.py
import razorpay
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Your RazorpayX Test Keys (from dashboard)
RAZORPAY_X_KEY = "rzp_test_RjQKo4DwGUWRL2"
RAZORPAY_X_SECRET = "jAz4I7qRwSYX9UyFrZIoxdGs"

# This is your RazorpayX-linked virtual account (test mode)
RAZORPAY_X_ACCOUNT_NUMBER = "2323230003681825"  # Fixed test account

client = razorpay.Client(auth=(RAZORPAY_X_KEY, RAZORPAY_X_SECRET))


def get_or_create_fund_account(rider):
    """Create or fetch RazorpayX Contact + Bank Account for rider"""

    print(hasattr(client, "contact"))      # → True
    print(hasattr(client, "payout"))
    try:
        # Step 1: Find contact by reference_id (your rider.id)
        contacts = client.contact.all({"reference_id": str(rider.id)})
        contact = contacts.get("items", [None])[0]

        if not contact:
            contact = client.contact.create({
                "name": rider.bank_holder_name or rider.user.full_name or "Rider",
                "email": rider.user.email or f"rider{rider.id}@example.com",
                "contact": rider.user.phone or "9999999999",
                "type": "employee",
                "reference_id": str(rider.id),
            })
            logger.info(f"Created RazorpayX contact for rider {rider.id}")

        # Step 2: Find or create fund account (bank)
        fund_accounts = client.fund_account.all({"contact_id": contact["id"]})
        fund_account = next(
            (fa for fa in fund_accounts.get("items", []) if fa.get("account_type") == "bank_account"),
            None
        )

        if not fund_account and rider.bank_account_number and rider.bank_ifsc:
            fund_account = client.fund_account.create({
                "contact_id": contact["id"],
                "account_type": "bank_account",
                "bank_account": {
                    "name": rider.bank_holder_name or rider.user.full_name,
                    "account_number": rider.bank_account_number,
                    "ifsc": rider.bank_ifsc,
                }
            })
            logger.info(f"Created fund account for rider {rider.id}")

        return fund_account

    except Exception as e:
        logger.error(f"Failed to setup fund account for rider {rider.id}: {e}")
        return None