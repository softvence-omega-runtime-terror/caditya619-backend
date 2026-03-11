from applications.earning.vendor_earning import Beneficiary
from applications.user.vendor import VendorProfile


BENEFICIARY_TEST_CASES = [
    {"account": "026291800001191", "ifsc": "YESB0000262", "expected": "Success"},
    {"account": "00011020001772", "ifsc": "HDFC0000001", "expected": "Success"},
    {"account": "1233943142", "ifsc": "ICIC0000009", "expected": "Success"},
    {"account": "388108022658", "ifsc": "ICIC0000009", "expected": "Success"},
    {"account": "000890289871772", "ifsc": "SCBL0036078", "expected": "Success"},
    {"account": "000100289877623", "ifsc": "SBIN0008752", "expected": "Success"},
    {"account": "2640101002729", "ifsc": "CNRR0002640", "expected": "Failure - Invaid IFSC code"},
    {"account": "026291800001190", "ifsc": "YESB0000262", "expected": "Failure - Invalid Account number"},
    {"account": "234005000876", "ifsc": "ICIC0000007", "expected": "Failure - Invalid Account number"},
    {"account": "1234567890", "ifsc": "ICIC0000001", "expected": "Failure - Invalid IFSC code"},
    {"account": "007711000031", "ifsc": "HDFC0000077", "expected": "Pending"},
    {"account": "00224412311300", "ifsc": "YESB0000001", "expected": "Pending (later to Success)"},
    {"account": "7766666351000", "ifsc": "YESB0000001", "expected": "Pending (later to Failure)"},
    {"account": "7766671735000", "ifsc": "SBIN0000004", "expected": "Success (later to Reversed)"},
    {"account": "02014457596969", "ifsc": "CITI0000001", "expected": "Success (later to Reversed)"},
    {
        "account": "34978321547298",
        "ifsc": "KKBK0000001",
        "expected": "Timeout - 25s (later to Success); test with 10s client timeout and 30s server timeout",
    },
    {"account": "9999999999", "ifsc": "WALLET_PAYTM", "expected": "Paytm successful wallet transfer"},
    {"account": "8888888888", "ifsc": "WALLET_PAYTM", "expected": "Paytm successful wallet transfer"},
    {"account": "7777777777", "ifsc": "WALLET_AMAZONPAY", "expected": "AmazonPay successful wallet transfer"},
    {"account": "6666666666", "ifsc": "WALLET_AMAZONPAY", "expected": "AmazonPay successful wallet transfer"},
]


async def create_dummy_beneficiaries_for_all_vendors():
    vendors = await VendorProfile.all()
    if not vendors:
        print("No vendor profiles found. Skipping dummy beneficiary creation.")
        return

    created_count = 0
    updated_count = 0

    for vendor in vendors:
        for idx, case in enumerate(BENEFICIARY_TEST_CASES, start=1):
            beneficiary_id = f"DUMMY-V{vendor.id}-{idx:03d}"
            expected_tag = case["expected"][:120]
            defaults = {
                "name": f"Dummy {idx:02d} - {expected_tag}",
                "bank_account_number": case["account"],
                "bank_ifsc": case["ifsc"],
                "email": f"vendor{vendor.id}.benef{idx}@dummy.test",
                "phone": f"90000{vendor.id:03d}{idx:03d}",
                "is_active": idx == 1,
            }

            beneficiary, created = await Beneficiary.get_or_create(
                vendor_id=vendor.id,
                beneficiary_id=beneficiary_id,
                defaults=defaults,
            )

            if created:
                created_count += 1
                continue

            changed_fields = []
            for field_name, value in defaults.items():
                if getattr(beneficiary, field_name) != value:
                    setattr(beneficiary, field_name, value)
                    changed_fields.append(field_name)

            if changed_fields:
                await beneficiary.save(update_fields=changed_fields)
                updated_count += 1

    print(
        "Dummy beneficiary sync completed. "
        f"vendors={len(vendors)}, cases_per_vendor={len(BENEFICIARY_TEST_CASES)}, "
        f"created={created_count}, updated={updated_count}"
    )
