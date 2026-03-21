import logging
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Sequence

from fastapi import UploadFile
from fastapi.templating import Jinja2Templates

from app.utils.file_manager import save_file

UPLOAD_FOLDER = "payout_invoices"
ORDER_INVOICE_UPLOAD_FOLDER = "order_invoices"

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


def _normalize_template_names(template_name: str | Sequence[str]) -> list[str]:
    if isinstance(template_name, str):
        return [template_name]
    return [name for name in template_name if name]


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    template = templates.get_template(template_name)
    return template.render(**context)


def _extract_tag_content(html: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _render_combined_html(template_names: list[str], context: dict[str, Any]) -> str:
    rendered_docs = [_render_template(name, context or {}) for name in template_names]
    if len(rendered_docs) == 1:
        return rendered_docs[0]

    head_parts: list[str] = []
    body_parts: list[str] = []

    for index, html in enumerate(rendered_docs):
        head_content = _extract_tag_content(html, "head")
        body_content = _extract_tag_content(html, "body") or html
        if head_content:
            head_parts.append(head_content)
        body_parts.append(body_content)
        if index < len(rendered_docs) - 1:
            body_parts.append('<div style="page-break-after: always;"></div>')

    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
        f"{''.join(head_parts)}</head><body>{''.join(body_parts)}</body></html>"
    )


def _render_pdf_bytes(html: str, base_url: str) -> bytes:
    try:
        from weasyprint import HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint is installed but its native libraries are missing. "
            "This Windows machine needs the GTK/Pango runtime that provides "
            "libgobject-2.0-0.dll before PDF generation can work."
        ) from exc
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not available in the current Python environment."
        ) from exc

    return HTML(string=html, base_url=base_url).write_pdf()


async def generate_pdf(
    template_name: str | Sequence[str],
    context: dict[str, Any],
    filename: str,
    upload_to: str = UPLOAD_FOLDER,
) -> str:
    template_names = _normalize_template_names(template_name)
    if not template_names:
        raise ValueError("At least one template name is required")
    html = _render_combined_html(template_names, context or {})
    base_url = os.path.abspath(".")
    pdf_bytes = _render_pdf_bytes(html, base_url)

    pdf_file = UploadFile(
        filename=filename,
        file=BytesIO(pdf_bytes)
    )

    file_url = await save_file(
        file=pdf_file,
        upload_to=upload_to,
        compress=False,
        allowed_extensions=["pdf"],
    )

    return file_url


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _format_amount(value: Any) -> str:
    return f"{_to_decimal(value):.2f}"


def _clean_lines(*values: Any) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def _join_non_empty(values: list[str], separator: str = ", ") -> str:
    return separator.join([value for value in values if value])


def _integer_to_words(number: int) -> str:
    ones = [
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    if number < 20:
        return ones[number]
    if number < 100:
        return tens[number // 10] + (f" {ones[number % 10]}" if number % 10 else "")
    if number < 1000:
        return ones[number // 100] + " Hundred" + (f" {_integer_to_words(number % 100)}" if number % 100 else "")
    if number < 100000:
        return _integer_to_words(number // 1000) + " Thousand" + (f" {_integer_to_words(number % 1000)}" if number % 1000 else "")
    if number < 10000000:
        return _integer_to_words(number // 100000) + " Lakh" + (f" {_integer_to_words(number % 100000)}" if number % 100000 else "")
    return _integer_to_words(number // 10000000) + " Crore" + (f" {_integer_to_words(number % 10000000)}" if number % 10000000 else "")


def _amount_in_words(value: Any) -> str:
    amount = _to_decimal(value).quantize(Decimal("0.01"))
    rupees = int(amount)
    paisa = int((amount - Decimal(rupees)) * 100)

    rupee_words = _integer_to_words(rupees) + " Rupees"
    paisa_words = (_integer_to_words(paisa) + " Paisa") if paisa else "Zero Paisa"
    return f"{rupee_words} And {paisa_words} Only"


def _build_shipping_lines(order) -> list[str]:
    shipping = getattr(order, "shipping_address", None)
    shipping_meta = (order.metadata or {}).get("shipping_address", {})

    city_state_country = _join_non_empty([
        getattr(shipping, "city", None) or shipping_meta.get("city", ""),
        getattr(shipping, "state", None) or shipping_meta.get("state", ""),
        getattr(shipping, "country", None) or shipping_meta.get("country", ""),
    ])

    return _clean_lines(
        getattr(shipping, "flat_house_building", None),
        getattr(shipping, "floor_number", None),
        getattr(shipping, "address_line1", None) or shipping_meta.get("address_line1", ""),
        getattr(shipping, "address_line2", None) or shipping_meta.get("address_line2", ""),
        getattr(shipping, "nearby_landmark", None),
        city_state_country,
        getattr(shipping, "postal_code", None) or shipping_meta.get("postal_code", ""),
    )


def _build_order_item_rows(order) -> tuple[list[dict[str, str]], dict[str, Decimal]]:
    rows: list[dict[str, str]] = []
    gross_total = Decimal("0.00")
    discount_total = Decimal("0.00")
    subtotal_total = Decimal("0.00")
    total_quantity = 0

    for index, order_item in enumerate(order.items, start=1):
        quantity = int(order_item.quantity or 0)
        unit_price = _to_decimal(order_item.price)
        catalog_price = _to_decimal(getattr(getattr(order_item, "item", None), "price", unit_price))
        gross_value = catalog_price * quantity
        discount_value = max((catalog_price - unit_price) * quantity, Decimal("0.00"))
        taxable_value = unit_price * quantity

        gross_total += gross_value
        discount_total += discount_value
        subtotal_total += taxable_value
        total_quantity += quantity

        rows.append({
            "sr_no": str(index),
            "particulars": f"{quantity} x {order_item.title}",
            "description": order_item.title,
            "product_name": order_item.title,
            "upc": str(order_item.item_id or ""),
            "hsn_code": "",
            "hsn": "",
            "manufacturer_name": "",
            "batch_no": "",
            "expiry_date": "",
            "qty": str(quantity),
            "gross_value": _format_amount(gross_value),
            "discount": _format_amount(discount_value),
            "discount_amount": _format_amount(discount_value),
            "net_value": _format_amount(taxable_value),
            "taxable_value": _format_amount(taxable_value),
            "original_mrp": _format_amount(catalog_price),
            "revised_mrp": _format_amount(unit_price),
            "mrp": _format_amount(catalog_price),
            "cgst_rate": "0.00",
            "cgst_amount": "0.00",
            "sgst_rate": "0.00",
            "sgst_amount": "0.00",
            "gst_rate": "0.00",
            "gst_amount": "0.00",
            "total": _format_amount(taxable_value),
            "total_amount": _format_amount(taxable_value),
            "particulars_class": "text-left",
        })

    totals = {
        "gross_total": gross_total,
        "discount_total": discount_total,
        "subtotal_total": subtotal_total,
        "total_quantity": Decimal(total_quantity),
    }
    return rows, totals


def _get_vendor_type(order) -> str:
    vendor_profile = getattr(getattr(order, "vendor", None), "vendor_profile", None)
    metadata_vendor_info = (order.metadata or {}).get("vendor_info", {})
    vendor_type = (
        getattr(vendor_profile, "type", None)
        or metadata_vendor_info.get("store_type")
    )
    if vendor_type:
        return str(vendor_type).lower()

    for order_item in getattr(order, "items", []):
        item = getattr(order_item, "item", None)
        category = getattr(item, "category", None)
        category_type = getattr(category, "type", None)
        if category_type:
            return str(category_type).lower()

    return "grocery"


def _get_invoice_template_names(vendor_type: str) -> tuple[str, str] | None:
    template_map = {
        "food": ("food_invoice1.html", "food_invoice2.html"),
        "grocery": ("grocery_invoice1.html", "grocery_invoice2.html"),
        "medicine": ("medecine_invoice1.html", "medecine_invoice2.html"),
        "medecine": ("medecine_invoice1.html", "medecine_invoice2.html"),
    }
    return template_map.get(vendor_type.lower())


def _build_invoice_context(order, vendor_type: str) -> dict[str, Any]:
    vendor = getattr(order, "vendor", None)
    vendor_profile = getattr(vendor, "vendor_profile", None)
    metadata_vendor_info = (order.metadata or {}).get("vendor_info", {})
    shipping = getattr(order, "shipping_address", None)
    shipping_meta = (order.metadata or {}).get("shipping_address", {})

    vendor_name = getattr(vendor, "name", "") or metadata_vendor_info.get("vendor_name", "")
    store_name = getattr(vendor_profile, "owner_name", "") or metadata_vendor_info.get("store_name", "") or vendor_name
    customer_name = (
        getattr(shipping, "full_name", None)
        or shipping_meta.get("full_name")
        or getattr(getattr(order, "user", None), "name", None)
        or "Customer"
    )
    customer_lines = _build_shipping_lines(order)
    customer_address = ", ".join(customer_lines)
    state = getattr(shipping, "state", None) or shipping_meta.get("state", "")
    order_date = getattr(order, "order_date", None) or datetime.utcnow()

    item_rows, item_totals = _build_order_item_rows(order)
    subtotal = _to_decimal(order.subtotal)
    delivery_fee = _to_decimal(order.delivery_fee)
    order_discount = _to_decimal(order.discount)
    total = _to_decimal(order.total)
    total_quantity = int(item_totals["total_quantity"])

    invoice_context = {
        "header": {
            "title": "Tax Invoice",
            "copy_label": "ORIGINAL FOR RECIPIENT",
        },
        "seller": {
            "heading": "Tax Invoice on behalf of -",
            "legal_entity_name": vendor_name,
            "restaurant_name": store_name,
            "restaurant_address": "",
            "restaurant_gstin": "",
            "restaurant_fssai": "",
            "invoice_number": order.id,
            "invoice_date": order_date.strftime("%d/%m/%Y"),
            "name": store_name or vendor_name,
            "address_lines": [],
            "details": [
                {"label": "Phone", "value": getattr(vendor, "phone", "") or ""},
                {"label": "Email", "value": getattr(vendor, "email", "") or ""},
                {"label": "Store Type", "value": vendor_type.title()},
            ],
            "invoice_number_label": order.id,
            "qr_image_url": "",
        },
        "customer": {
            "heading": "Invoice To",
            "name": customer_name,
            "delivery_address": customer_address,
            "place_of_supply": state,
            "address_lines": customer_lines,
            "pincode": getattr(shipping, "postal_code", None) or shipping_meta.get("postal_code", ""),
            "state": state,
            "address": customer_address,
            "patient_name": customer_name,
            "contact": getattr(shipping, "phone_number", None) or shipping_meta.get("phone_number", ""),
            "doctor_name_address": "",
        },
        "order": {
            "order_id": order.id,
            "invoice_date": order_date.strftime("%d-%m-%Y"),
            "place_of_supply": state,
        },
        "service": {
            "hsn_code": "",
            "description": "Restaurant Service" if vendor_type == "food" else vendor_type.title(),
        },
        "line_items": item_rows,
        "additional_rows": [
            {
                "particulars": "Items (total)",
                "gross_value": _format_amount(item_totals["gross_total"]),
                "discount": _format_amount(item_totals["discount_total"]),
                "net_value": _format_amount(subtotal),
                "cgst_rate": "",
                "cgst_amount": "0.00",
                "sgst_rate": "",
                "sgst_amount": "0.00",
                "total": _format_amount(subtotal),
                "particulars_class": "text-left bold",
            }
        ],
        "total_row": {
            "label": "Total",
            "particulars": "Total Value",
            "gross_value": _format_amount(item_totals["gross_total"] + delivery_fee),
            "discount": _format_amount(item_totals["discount_total"] + order_discount),
            "net_value": _format_amount(total),
            "taxable_value": _format_amount(subtotal),
            "qty": str(total_quantity),
            "cgst_amount": "0.00",
            "sgst_amount": "0.00",
            "total": _format_amount(total),
        },
        "amount": {
            "in_words": _amount_in_words(total),
        },
        "footer": {
            "amount_in_words": _amount_in_words(total),
            "settlement_text": (
                f"Amount of INR {_format_amount(total)} settled digitally against "
                f"Order ID {order.id} dated {order_date.strftime('%Y-%m-%d')}."
            ),
            "reverse_charge": "No",
            "company_name": store_name or vendor_name,
            "details": [
                {"label": "Phone", "value": getattr(vendor, "phone", "") or ""},
                {"label": "Email", "value": getattr(vendor, "email", "") or ""},
                {"label": "Order", "value": order.id},
            ],
            "signatory_label": "Authorised Signatory",
        },
        "meta": {
            "invoice_number": order.id,
            "invoice_date": order_date.strftime("%Y-%m-%d"),
            "order_id": order.id,
            "qr_image_url": "",
            "qr_caption": "For Compliance Purpose",
            "delivery_confirmation_otp": "",
            "reverse_charge": "No",
        },
        "terms": [
            "If you have any issues or queries, contact support.",
            "Please keep this invoice for your records.",
            "Do not share payment credentials with anyone.",
        ],
    }

    if delivery_fee > 0:
        invoice_context["additional_rows"].append({
            "particulars": "Delivery Charge",
            "gross_value": _format_amount(delivery_fee),
            "discount": "0.00",
            "net_value": _format_amount(delivery_fee),
            "cgst_rate": "0.00",
            "cgst_amount": "0.00",
            "sgst_rate": "0.00",
            "sgst_amount": "0.00",
            "total": _format_amount(delivery_fee),
            "particulars_class": "text-left",
        })

    if vendor_type in {"medicine", "medecine"}:
        invoice_context["header"]["title"] = "Tax Invoice/Bill of Supply/Cash Memo (Original for Recipient)"
        invoice_context["seller"].update({
            "name": store_name or vendor_name,
            "dl_number": "",
            "fssai_license_number": "",
            "gst": "",
            "registered_address": "",
            "premise_address": "",
        })
        if delivery_fee > 0:
            invoice_context["line_items"].append({
                "sr_no": str(len(invoice_context["line_items"]) + 1),
                "product_name": "Handling Charges",
                "manufacturer_name": "",
                "batch_no": "",
                "expiry_date": "",
                "qty": "1",
                "original_mrp": _format_amount(delivery_fee),
                "revised_mrp": _format_amount(delivery_fee),
                "discount_amount": "0.00",
                "taxable_amount": _format_amount(delivery_fee),
                "hsn": "",
                "gst_rate": "0.00",
                "gst_amount": "0.00",
                "total_amount": _format_amount(delivery_fee),
            })

    return {"invoice": invoice_context}


async def generate_order_invoice_pdf(order_id: str) -> dict[str, str | None] | None:
    from applications.customer.models import Order

    order = await Order.get_or_none(id=order_id).prefetch_related(
        "user",
        "vendor__vendor_profile",
        "shipping_address",
        "items__item__category",
    )
    if not order:
        logger.warning("Skipping invoice generation; order %s not found", order_id)
        return None

    if order.invoice1 and order.invoice2:
        return {
            "invoice1": order.invoice1,
            "invoice2": order.invoice2,
        }

    vendor_type = _get_vendor_type(order)
    template_names = _get_invoice_template_names(vendor_type)
    if not template_names:
        logger.warning("Skipping invoice generation; unsupported vendor type '%s' for order %s", vendor_type, order_id)
        return None

    context = _build_invoice_context(order, vendor_type)
    template_field_pairs = (
        ("invoice1", template_names[0], f"{order.id}_{vendor_type}_invoice1.pdf"),
        ("invoice2", template_names[1], f"{order.id}_{vendor_type}_invoice2.pdf"),
    )
    update_fields: list[str] = []

    for field_name, template_name, filename in template_field_pairs:
        if getattr(order, field_name):
            continue
        try:
            file_url = await generate_pdf(
                template_name=template_name,
                context=context,
                filename=filename,
                upload_to=ORDER_INVOICE_UPLOAD_FOLDER,
            )
        except Exception:
            logger.exception("Failed to generate %s PDF for order %s", field_name, order_id)
            continue

        setattr(order, field_name, file_url)
        update_fields.append(field_name)

    if update_fields:
        await order.save(update_fields=list(dict.fromkeys(update_fields)))

    return {
        "invoice1": order.invoice1,
        "invoice2": order.invoice2,
    }
