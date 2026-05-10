import datetime
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    AttendanceRawRow,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    PaymentMethod,
    PricingOption,
    ReportImport,
    SaleLine,
    SaleLineVersion,
    SaleRawRow,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    ServicePurchaseVersion,
    StaffMember,
    Studio,
)


SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

ATTENDANCE_REPORT_TYPE = "attendance_with_revenue"
SALES_REPORT_TYPE = "sales"
SALES_BY_SERVICE_REPORT_TYPE = "sales_by_service"
SUPPORTED_REPORT_TYPES = [ATTENDANCE_REPORT_TYPE, SALES_REPORT_TYPE, SALES_BY_SERVICE_REPORT_TYPE]

ATTENDANCE_REQUIRED_HEADERS = [
    "Fecha",
    "Día de la semana",
    "Tiempo",
    "ID del cliente",
    "Cliente",
    "Visita por categoría de servicio",
    "Tipo de Visita",
    "Tipo",
    "Opción de precio",
    "Fecha de Exp.",
    "Visitas Rest.",
    "Personal",
    "Ubicación de visita",
    "Ubicación de venta",
    "Personal pagado",
    "Cancelación tardíá",
    "No presentado",
    "Metodo de programación",
    "Método de pago",
    "Ingresos por visita",
    "Pago de categoría de servicio",
]

SALES_REQUIRED_HEADERS = [
    "Fecha de Venta",
    "ID del Cliente",
    "Cliente",
    "No. de Venta",
    "Nombre del artículo",
    "Notas de Venta",
    "Localidad",
    "Notas",
    "Color",
    "Tamaño",
    "Precio del artículo (excluyendo impuestos)",
    "Cantidad",
    "Sub-total (excluyendo impuestos)",
    "Descuento en %",
    "Cantidad de descuento",
    "Impuesto",
    "Total de artículos",
    "Total Pagado con Método de Pago",
    "Forma de Pago",
]

SALES_OPTIONAL_HEADERS = ["Computación #"]

SALES_BY_SERVICE_REQUIRED_HEADERS = [
    "Nombre",
    "ID del Cliente",
    "Cliente",
    "Categoría",
    "Teléfono particular",
    "Fecha de Venta",
    "Fecha de activación",
    "Días de activación de compensación",
    "Fecha de Expiración",
    "Cantidad total",
    "Equivalente en efectivo",
    "No equivalente de efectivo",
    "Cantidad",
]


def clean_value(value):
    return str(value if value is not None else "").replace("\xa0", " ").strip()


def normalize_name(value):
    return clean_value(value).casefold()


def display_name_part(value):
    raw = clean_value(value)
    if not raw:
        return ""
    small_words = {"de", "del", "de la", "la", "las", "los", "y", "da", "do", "dos"}
    words = []
    for word in raw.lower().split():
        words.append(word if word in small_words else word[:1].upper() + word[1:])
    return " ".join(words)


def split_client_name(mindbody_name):
    raw = clean_value(mindbody_name)
    if "," in raw:
        last_name, first_name = [part.strip() for part in raw.split(",", 1)]
        return display_name_part(first_name), display_name_part(last_name)
    parts = display_name_part(raw).split()
    if len(parts) <= 1:
        return display_name_part(raw), ""
    return " ".join(parts[:-1]), parts[-1]


def split_staff_name(mindbody_name):
    raw = clean_value(mindbody_name)
    if "," in raw:
        return split_client_name(raw)
    parts = display_name_part(raw).split()
    if len(parts) <= 1:
        return display_name_part(raw), ""
    return parts[0], " ".join(parts[1:])


def person_defaults(model, name, extra_defaults):
    if model not in (Client, StaffMember):
        return {"name": clean_value(name), **extra_defaults}

    first_name, last_name = split_client_name(name) if model is Client else split_staff_name(name)
    display_name = " ".join(part for part in (first_name, last_name) if part).strip() or display_name_part(name)
    return {
        "name": display_name,
        "first_name": first_name,
        "last_name": last_name,
        **extra_defaults,
    }


def parse_number(value):
    raw = clean_value(value)
    if raw in ("", "N/A", "---"):
        return None
    try:
        return float(raw)
    except ValueError:
        try:
            return float(raw.replace(".", "").replace(",", "."))
        except ValueError:
            return None


def parse_excel_date(value):
    number = parse_number(value)
    if number is None:
        return None
    try:
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=number)
    except (OverflowError, ValueError):
        return None


def parse_yes_no(value):
    raw = normalize_name(value)
    if raw in ("sí", "si", "yes", "true"):
        return True
    if raw in ("no", "false"):
        return False
    return None


def column_number(cell_ref):
    match = re.match(r"([A-Z]+)", cell_ref)
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value = cell.find(SPREADSHEET_NS + "v")
    inline = cell.find(SPREADSHEET_NS + "is")

    if cell_type == "s" and value is not None:
        return shared_strings[int(value.text)]
    if cell_type == "inlineStr" and inline is not None:
        return "".join(text.text or "" for text in inline.iter(SPREADSHEET_NS + "t"))
    return value.text if value is not None else ""


def load_first_sheet_rows(uploaded_file):
    uploaded_file.seek(0)
    with zipfile.ZipFile(uploaded_file) as workbook_zip:
        shared_strings = []
        try:
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(SPREADSHEET_NS + "si"):
                shared_strings.append("".join(text.text or "" for text in item.iter(SPREADSHEET_NS + "t")))
        except KeyError:
            pass

        workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        rels = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        first_sheet = workbook.find(SPREADSHEET_NS + "sheets").findall(SPREADSHEET_NS + "sheet")[0]
        target = rel_map[first_sheet.attrib[RELATIONSHIP_NS + "id"]]
        if not target.startswith("worksheets/"):
            target = f"worksheets/{target.split('/')[-1]}"

        worksheet = ET.fromstring(workbook_zip.read(f"xl/{target}"))
        parsed_rows = []
        for row in worksheet.find(SPREADSHEET_NS + "sheetData").findall(SPREADSHEET_NS + "row"):
            row_values = {}
            for cell in row.findall(SPREADSHEET_NS + "c"):
                row_values[column_number(cell.attrib["r"])] = cell_value(cell, shared_strings)
            if row_values:
                parsed_rows.append((int(row.attrib.get("r", "0")), row_values))

        return first_sheet.attrib["name"], parsed_rows


def row_hash(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_parts(parts):
    serialized = json.dumps([clean_value(part) for part in parts], ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def assign_occurrence_indexes(rows, base_key_builder):
    occurrence_counts = Counter()
    for row in rows:
        base_key = base_key_builder(row["payload"])
        occurrence_counts[base_key] += 1
        row["payload"]["_occurrence_index"] = occurrence_counts[base_key]
        row["hash"] = row_hash(row["payload"])
    return rows


def table_from_rows(parsed_rows):
    header_index = None
    for index, (_, row_values) in enumerate(parsed_rows):
        populated_cells = sum(bool(clean_value(value)) for value in row_values.values())
        if populated_cells >= 3:
            header_index = index
            break

    if header_index is None:
        return [], []

    max_column = max(parsed_rows[header_index][1].keys())
    headers = [clean_value(parsed_rows[header_index][1].get(index, "")) for index in range(1, max_column + 1)]
    data_rows = []
    for row_number, row_values in parsed_rows[header_index + 1:]:
        payload = {
            headers[index - 1] or f"col_{index}": row_values.get(index, "")
            for index in range(1, max_column + 1)
        }
        if any(clean_value(value) for value in payload.values()):
            data_rows.append({"row_number": row_number, "payload": payload})

    return headers, data_rows


def build_lookup_preview(site, data_rows):
    client_ids = {
        clean_value(row["payload"].get("ID del cliente"))
        for row in data_rows
        if clean_value(row["payload"].get("ID del cliente"))
    }
    studio_names = {
        clean_value(row["payload"].get(field))
        for row in data_rows
        for field in ("Ubicación de visita", "Ubicación de venta")
        if clean_value(row["payload"].get(field)) not in ("", "N/A")
    }
    staff_names = {
        clean_value(row["payload"].get("Personal"))
        for row in data_rows
        if clean_value(row["payload"].get("Personal")) not in ("", "N/A")
    }
    service_category_names = {
        clean_value(row["payload"].get(field))
        for row in data_rows
        for field in ("Visita por categoría de servicio", "Pago de categoría de servicio")
        if clean_value(row["payload"].get(field)) not in ("", "N/A")
    }
    pricing_option_names = {
        clean_value(row["payload"].get("Opción de precio"))
        for row in data_rows
        if clean_value(row["payload"].get("Opción de precio")) not in ("", "N/A")
    }
    payment_method_names = {
        clean_value(row["payload"].get("Método de pago"))
        for row in data_rows
        if clean_value(row["payload"].get("Método de pago")) not in ("", "N/A")
    }

    existing_client_ids = set(
        Client.objects.filter(site=site, mindbody_id__in=client_ids).values_list("mindbody_id", flat=True)
    )

    def existing_normalized(model, names):
        normalized_values = [name.casefold() for name in names]
        return set(
            model.objects.filter(site=site, normalized_name__in=normalized_values)
            .values_list("normalized_name", flat=True)
        )

    existing_studios = existing_normalized(Studio, studio_names)
    existing_staff = existing_normalized(StaffMember, staff_names)
    existing_categories = existing_normalized(ServiceCategory, service_category_names)
    existing_pricing_options = existing_normalized(PricingOption, pricing_option_names)
    existing_payment_methods = existing_normalized(PaymentMethod, payment_method_names)

    def new_names(names, existing):
        return sorted(name for name in names if name.casefold() not in existing)

    return {
        "clients": {
            "total": len(client_ids),
            "new": len(client_ids - existing_client_ids),
            "sample_new": sorted(client_ids - existing_client_ids)[:10],
        },
        "studios": {
            "total": len(studio_names),
            "new": len(new_names(studio_names, existing_studios)),
            "sample_new": new_names(studio_names, existing_studios)[:10],
        },
        "staff_members": {
            "total": len(staff_names),
            "new": len(new_names(staff_names, existing_staff)),
            "sample_new": new_names(staff_names, existing_staff)[:10],
        },
        "service_categories": {
            "total": len(service_category_names),
            "new": len(new_names(service_category_names, existing_categories)),
            "sample_new": new_names(service_category_names, existing_categories)[:10],
        },
        "pricing_options": {
            "total": len(pricing_option_names),
            "new": len(new_names(pricing_option_names, existing_pricing_options)),
            "sample_new": new_names(pricing_option_names, existing_pricing_options)[:10],
        },
        "payment_methods": {
            "total": len(payment_method_names),
            "new": len(new_names(payment_method_names, existing_payment_methods)),
            "sample_new": new_names(payment_method_names, existing_payment_methods)[:10],
        },
    }


def preview_attendance_report(uploaded_file, site):
    sheet_name, parsed_rows = load_first_sheet_rows(uploaded_file)
    headers, rows = table_from_rows(parsed_rows)

    missing_headers = [header for header in ATTENDANCE_REQUIRED_HEADERS if header not in headers]
    extra_headers = [header for header in headers if header not in ATTENDANCE_REQUIRED_HEADERS]

    footer_rows = []
    data_rows = []
    for row in rows:
        if clean_value(row["payload"].get("Fecha")).casefold() in ("total", "totales"):
            footer_rows.append(row)
        else:
            data_rows.append(row)

    valid_rows = []
    invalid_rows = []
    for row in data_rows:
        payload = row["payload"]
        errors = []
        visit_date = parse_excel_date(payload.get("Fecha"))
        if not visit_date:
            errors.append("Invalid Fecha")
        if not clean_value(payload.get("ID del cliente")):
            errors.append("Missing ID del cliente")
        if not clean_value(payload.get("Cliente")):
            errors.append("Missing Cliente")
        if not clean_value(payload.get("Ubicación de visita")):
            errors.append("Missing Ubicación de visita")
        revenue = parse_number(payload.get("Ingresos por visita"))
        if revenue is None:
            errors.append("Invalid Ingresos por visita")

        normalized_payload = {key: clean_value(value) for key, value in payload.items()}
        normalized_payload["_visit_date"] = visit_date.isoformat() if visit_date else None
        normalized_payload["_expiration_date"] = (
            parse_excel_date(payload.get("Fecha de Exp.")).isoformat()
            if parse_excel_date(payload.get("Fecha de Exp."))
            else None
        )
        normalized_payload["_late_cancel"] = parse_yes_no(payload.get("Cancelación tardíá"))
        normalized_payload["_no_show"] = parse_yes_no(payload.get("No presentado"))
        normalized_payload["_revenue"] = revenue

        enriched_row = {
            "row_number": row["row_number"],
            "hash": row_hash(normalized_payload),
            "payload": normalized_payload,
            "errors": errors,
        }
        if errors:
            invalid_rows.append(enriched_row)
        else:
            valid_rows.append(enriched_row)

    hash_counts = Counter(row["hash"] for row in valid_rows)
    duplicate_groups = sum(1 for count in hash_counts.values() if count > 1)
    duplicate_extra_rows = sum(count - 1 for count in hash_counts.values() if count > 1)

    date_values = [
        parse_excel_date(row["payload"].get("Fecha"))
        for row in data_rows
        if parse_excel_date(row["payload"].get("Fecha"))
    ]
    revenue_values = [row["payload"]["_revenue"] for row in valid_rows if row["payload"]["_revenue"] is not None]

    late_cancel_count = sum(row["payload"]["_late_cancel"] is True for row in valid_rows)
    no_show_count = sum(row["payload"]["_no_show"] is True for row in valid_rows)
    attended_count = sum(
        row["payload"]["_late_cancel"] is not True and row["payload"]["_no_show"] is not True
        for row in valid_rows
    )
    sample_fields = [
        "Fecha",
        "Tiempo",
        "ID del cliente",
        "Cliente",
        "Personal",
        "Ubicación de visita",
        "Tipo de Visita",
        "Opción de precio",
    ]

    return {
        "report_type": ATTENDANCE_REPORT_TYPE,
        "sheet_name": sheet_name,
        "headers": headers,
        "missing_headers": missing_headers,
        "extra_headers": extra_headers,
        "is_valid_schema": not missing_headers,
        "row_counts": {
            "raw_rows": len(rows),
            "data_rows": len(data_rows),
            "footer_rows": len(footer_rows),
            "valid_rows": len(valid_rows),
            "invalid_rows": len(invalid_rows),
            "duplicate_groups": duplicate_groups,
            "duplicate_extra_rows": duplicate_extra_rows,
        },
        "date_range": {
            "from": min(date_values).isoformat() if date_values else None,
            "to": max(date_values).isoformat() if date_values else None,
        },
        "attendance": {
            "attended_inferred": attended_count,
            "late_cancel": late_cancel_count,
            "no_show": no_show_count,
        },
        "revenue": {
            "total": round(sum(revenue_values), 2),
            "zero_revenue_rows": sum(value == 0 for value in revenue_values),
        },
        "lookup_preview": build_lookup_preview(site, valid_rows),
        "data_quality": {
            "requires_review": duplicate_extra_rows > 0,
            "repeated_row_samples": repeated_row_samples(valid_rows, sample_fields),
            "natural_key_collision_samples": natural_key_collision_samples(
                valid_rows,
                lambda payload: attendance_natural_key(site, payload),
                sample_fields,
            ),
            "import_impact": current_record_impact(
                valid_rows,
                AttendanceVisit,
                lambda payload: attendance_natural_key(site, payload),
            ),
        },
        "invalid_row_samples": invalid_rows[:10],
        "sample_rows": valid_rows[:5],
    }


def get_or_create_scoped(model, site, name, mindbody_id=None, **extra_defaults):
    cleaned_name = clean_value(name)
    if not cleaned_name or cleaned_name == "N/A":
        return None, False
    defaults = person_defaults(model, cleaned_name, extra_defaults)
    defaults["mindbody_name"] = cleaned_name
    defaults["normalized_name"] = normalize_name(defaults["name"])

    if mindbody_id:
        obj, created = model.objects.get_or_create(
            site=site,
            mindbody_id=clean_value(mindbody_id),
            defaults=defaults,
        )
        return obj, created

    obj = model.objects.filter(site=site, normalized_name=defaults["normalized_name"]).first()
    if obj:
        return obj, False

    return model.objects.create(
        site=site,
        **defaults,
    ), True


def parse_int(value):
    number = parse_number(value)
    if number is None:
        return None
    return int(number)


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def decimal_string(value):
    return str(money(value))


def build_sales_lookup_preview(site, valid_rows):
    client_ids = {
        clean_value(row["payload"].get("ID del Cliente"))
        for row in valid_rows
        if clean_value(row["payload"].get("ID del Cliente"))
    }
    studio_names = {
        clean_value(row["payload"].get("Localidad"))
        for row in valid_rows
        if clean_value(row["payload"].get("Localidad")) not in ("", "N/A")
    }
    payment_method_names = {
        clean_value(row["payload"].get("Forma de Pago"))
        for row in valid_rows
        if clean_value(row["payload"].get("Forma de Pago")) not in ("", "N/A")
    }

    existing_client_ids = set(
        Client.objects.filter(site=site, mindbody_id__in=client_ids).values_list("mindbody_id", flat=True)
    )

    def existing_normalized(model, names):
        normalized_values = [name.casefold() for name in names]
        return set(
            model.objects.filter(site=site, normalized_name__in=normalized_values)
            .values_list("normalized_name", flat=True)
        )

    existing_studios = existing_normalized(Studio, studio_names)
    existing_payment_methods = existing_normalized(PaymentMethod, payment_method_names)

    def new_names(names, existing):
        return sorted(name for name in names if name.casefold() not in existing)

    return {
        "clients": {
            "total": len(client_ids),
            "new": len(client_ids - existing_client_ids),
            "sample_new": sorted(client_ids - existing_client_ids)[:10],
        },
        "studios": {
            "total": len(studio_names),
            "new": len(new_names(studio_names, existing_studios)),
            "sample_new": new_names(studio_names, existing_studios)[:10],
        },
        "payment_methods": {
            "total": len(payment_method_names),
            "new": len(new_names(payment_method_names, existing_payment_methods)),
            "sample_new": new_names(payment_method_names, existing_payment_methods)[:10],
        },
    }


def build_service_purchase_lookup_preview(site, valid_rows):
    client_ids = {
        clean_value(row["payload"].get("ID del Cliente"))
        for row in valid_rows
        if clean_value(row["payload"].get("ID del Cliente"))
    }
    service_category_names = {
        clean_value(row["payload"].get("Categoría"))
        for row in valid_rows
        if clean_value(row["payload"].get("Categoría")) not in ("", "N/A")
    }
    pricing_option_names = {
        clean_value(row["payload"].get("Nombre"))
        for row in valid_rows
        if clean_value(row["payload"].get("Nombre")) not in ("", "N/A")
    }

    existing_client_ids = set(
        Client.objects.filter(site=site, mindbody_id__in=client_ids).values_list("mindbody_id", flat=True)
    )

    def existing_normalized(model, names):
        normalized_values = [name.casefold() for name in names]
        return set(
            model.objects.filter(site=site, normalized_name__in=normalized_values)
            .values_list("normalized_name", flat=True)
        )

    existing_categories = existing_normalized(ServiceCategory, service_category_names)
    existing_pricing_options = existing_normalized(PricingOption, pricing_option_names)

    def new_names(names, existing):
        return sorted(name for name in names if name.casefold() not in existing)

    return {
        "clients": {
            "total": len(client_ids),
            "new": len(client_ids - existing_client_ids),
            "sample_new": sorted(client_ids - existing_client_ids)[:10],
        },
        "service_categories": {
            "total": len(service_category_names),
            "new": len(new_names(service_category_names, existing_categories)),
            "sample_new": new_names(service_category_names, existing_categories)[:10],
        },
        "pricing_options": {
            "total": len(pricing_option_names),
            "new": len(new_names(pricing_option_names, existing_pricing_options)),
            "sample_new": new_names(pricing_option_names, existing_pricing_options)[:10],
        },
    }


def attendance_natural_key(site, payload):
    return hash_parts([
        site.id,
        payload.get("ID del cliente"),
        payload.get("_visit_date"),
        payload.get("Tiempo"),
        payload.get("Ubicación de visita"),
        payload.get("Personal"),
        payload.get("Visita por categoría de servicio"),
        payload.get("Tipo de Visita"),
    ])


def attendance_snapshot(payload, related):
    return {
        "site_id": related["site"].id,
        "client_id": related["client"].id,
        "staff_member_id": related["staff_member"].id if related["staff_member"] else None,
        "visit_studio_id": related["visit_studio"].id,
        "sale_studio_id": related["sale_studio"].id if related["sale_studio"] else None,
        "service_category_id": related["service_category"].id if related["service_category"] else None,
        "pricing_option_id": related["pricing_option"].id if related["pricing_option"] else None,
        "payment_method_id": related["payment_method"].id if related["payment_method"] else None,
        "visit_date": payload.get("_visit_date"),
        "visit_time_raw": payload.get("Tiempo"),
        "weekday_raw": payload.get("Día de la semana"),
        "visit_type": payload.get("Tipo de Visita"),
        "type_name": payload.get("Tipo"),
        "expiration_date": payload.get("_expiration_date"),
        "remaining_visits": parse_int(payload.get("Visitas Rest.")),
        "staff_paid": payload.get("_staff_paid"),
        "late_cancel": payload.get("_late_cancel") is True,
        "no_show": payload.get("_no_show") is True,
        "scheduling_method": payload.get("Metodo de programación"),
        "revenue": str(Decimal(str(payload.get("_revenue") or 0)).quantize(Decimal("0.01"))),
    }


def changed_fields(previous, current):
    if not previous:
        return []
    return sorted(key for key, value in current.items() if previous.get(key) != value)


def compact_payload(payload, fields):
    return {field: payload.get(field) for field in fields if payload.get(field) not in ("", None)}


def repeated_row_samples(valid_rows, sample_fields, max_samples=50):
    grouped = {}
    for row in valid_rows:
        grouped.setdefault(row["hash"], []).append(row)

    samples = []
    for rows in grouped.values():
        if len(rows) <= 1:
            continue
        samples.append({
            "count": len(rows),
            "row_numbers": [row["row_number"] for row in rows[:10]],
            "payload": compact_payload(rows[0]["payload"], sample_fields),
        })
        if len(samples) == max_samples:
            break
    return samples


def current_record_impact(valid_rows, model, natural_key_builder):
    current_candidates = {}
    for row in valid_rows:
        current_candidates[natural_key_builder(row["payload"])] = row

    existing = {
        item.natural_key: item.current_row_hash
        for item in model.objects.filter(natural_key__in=current_candidates.keys())
    }
    to_create = 0
    to_update = 0
    unchanged = 0

    for natural_key, row in current_candidates.items():
        current_hash = existing.get(natural_key)
        if current_hash is None:
            to_create += 1
        elif current_hash == row["hash"]:
            unchanged += 1
        else:
            to_update += 1

    return {
        "raw_rows_to_save": len(valid_rows),
        "current_records_to_create": to_create,
        "current_records_to_update": to_update,
        "current_records_unchanged": unchanged,
        "current_records_in_file": len(current_candidates),
        "natural_key_collisions": len(valid_rows) - len(current_candidates),
    }


def natural_key_collision_samples(valid_rows, natural_key_builder, sample_fields, max_samples=50):
    grouped = {}
    for row in valid_rows:
        grouped.setdefault(natural_key_builder(row["payload"]), []).append(row)

    samples = []
    for rows in grouped.values():
        if len(rows) <= 1:
            continue
        samples.append({
            "count": len(rows),
            "row_numbers": [row["row_number"] for row in rows[:10]],
            "payload": compact_payload(rows[0]["payload"], sample_fields),
        })
        if len(samples) == max_samples:
            break
    return samples


@transaction.atomic
def import_attendance_report(uploaded_file, site, uploaded_by=None):
    preview = preview_attendance_report(uploaded_file, site)
    if not preview["is_valid_schema"]:
        raise ValueError(f"Missing required headers: {', '.join(preview['missing_headers'])}")

    report_import = ReportImport.objects.create(
        report_type=ATTENDANCE_REPORT_TYPE,
        source_system="mindbody",
        file_name=getattr(uploaded_file, "name", "uploaded.xlsx"),
        status=ReportImport.STATUS_PROCESSING,
        total_rows=preview["row_counts"]["data_rows"],
        valid_rows=preview["row_counts"]["valid_rows"],
        error_rows=preview["row_counts"]["invalid_rows"],
        uploaded_by=uploaded_by,
    )

    stats = {
        "report_import_id": report_import.id,
        "raw_rows_created": 0,
        "attendance_created": 0,
        "attendance_changed": 0,
        "attendance_identical": 0,
        "natural_key_collisions": 0,
        "versions_created": 0,
        "new_lookups": {
            "clients": 0,
            "studios": 0,
            "staff_members": 0,
            "service_categories": 0,
            "pricing_options": 0,
            "payment_methods": 0,
        },
    }

    rows_to_import = preview_attendance_rows(uploaded_file)
    current_visit_candidates = {}

    for row in rows_to_import["valid_rows"]:
        payload = row["payload"]

        client, created = get_or_create_scoped(
            Client,
            site,
            payload.get("Cliente"),
            mindbody_id=payload.get("ID del cliente"),
        )
        stats["new_lookups"]["clients"] += int(created)

        visit_studio, created = get_or_create_scoped(Studio, site, payload.get("Ubicación de visita"))
        stats["new_lookups"]["studios"] += int(created)

        sale_studio, created = get_or_create_scoped(Studio, site, payload.get("Ubicación de venta"))
        stats["new_lookups"]["studios"] += int(created)

        staff_member, created = get_or_create_scoped(StaffMember, site, payload.get("Personal"))
        stats["new_lookups"]["staff_members"] += int(created)

        service_category, created = get_or_create_scoped(
            ServiceCategory,
            site,
            payload.get("Visita por categoría de servicio"),
        )
        stats["new_lookups"]["service_categories"] += int(created)

        pricing_option, created = get_or_create_scoped(
            PricingOption,
            site,
            payload.get("Opción de precio"),
            service_category=service_category,
        )
        stats["new_lookups"]["pricing_options"] += int(created)

        payment_method, created = get_or_create_scoped(PaymentMethod, site, payload.get("Método de pago"))
        stats["new_lookups"]["payment_methods"] += int(created)

        raw_row = AttendanceRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=payload,
            is_valid=True,
            validation_errors=[],
        )
        stats["raw_rows_created"] += 1

        related = {
            "site": site,
            "client": client,
            "staff_member": staff_member,
            "visit_studio": visit_studio,
            "sale_studio": sale_studio,
            "service_category": service_category,
            "pricing_option": pricing_option,
            "payment_method": payment_method,
        }
        natural_key = attendance_natural_key(site, payload)
        current_visit_candidates[natural_key] = {
            "row": row,
            "payload": payload,
            "raw_row": raw_row,
            "related": related,
        }

    for natural_key, candidate in current_visit_candidates.items():
        row = candidate["row"]
        payload = candidate["payload"]
        raw_row = candidate["raw_row"]
        related = candidate["related"]
        snapshot = attendance_snapshot(payload, related)

        visit = AttendanceVisit.objects.filter(natural_key=natural_key).first()
        previous_snapshot = None
        if visit:
            previous_version = visit.versions.order_by("-created_at").first()
            previous_snapshot = previous_version.snapshot if previous_version else None

        changes = changed_fields(previous_snapshot, snapshot)

        if not visit:
            visit = AttendanceVisit.objects.create(
                site=site,
                natural_key=natural_key,
                current_row_hash=row["hash"],
                client=related["client"],
                staff_member=related["staff_member"],
                visit_studio=related["visit_studio"],
                sale_studio=related["sale_studio"],
                service_category=related["service_category"],
                pricing_option=related["pricing_option"],
                payment_method=related["payment_method"],
                visit_date=payload["_visit_date"],
                visit_time_raw=payload.get("Tiempo") or "",
                weekday_raw=payload.get("Día de la semana"),
                visit_type=payload.get("Tipo de Visita"),
                type_name=payload.get("Tipo"),
                expiration_date=payload.get("_expiration_date"),
                remaining_visits=parse_int(payload.get("Visitas Rest.")),
                staff_paid=payload.get("_staff_paid"),
                late_cancel=payload.get("_late_cancel") is True,
                no_show=payload.get("_no_show") is True,
                scheduling_method=payload.get("Metodo de programación"),
                revenue=Decimal(str(payload.get("_revenue") or 0)).quantize(Decimal("0.01")),
                first_seen_import=report_import,
                last_seen_import=report_import,
                source_raw_row=raw_row,
            )
            stats["attendance_created"] += 1
            changes = list(snapshot.keys())
        elif visit.current_row_hash == row["hash"]:
            visit.last_seen_import = report_import
            visit.source_raw_row = raw_row
            visit.save(update_fields=["last_seen_import", "source_raw_row", "updated_at"])
            stats["attendance_identical"] += 1
        else:
            visit.current_row_hash = row["hash"]
            visit.client = related["client"]
            visit.staff_member = related["staff_member"]
            visit.visit_studio = related["visit_studio"]
            visit.sale_studio = related["sale_studio"]
            visit.service_category = related["service_category"]
            visit.pricing_option = related["pricing_option"]
            visit.payment_method = related["payment_method"]
            visit.visit_date = payload["_visit_date"]
            visit.visit_time_raw = payload.get("Tiempo") or ""
            visit.weekday_raw = payload.get("Día de la semana")
            visit.visit_type = payload.get("Tipo de Visita")
            visit.type_name = payload.get("Tipo")
            visit.expiration_date = payload.get("_expiration_date")
            visit.remaining_visits = parse_int(payload.get("Visitas Rest."))
            visit.staff_paid = payload.get("_staff_paid")
            visit.late_cancel = payload.get("_late_cancel") is True
            visit.no_show = payload.get("_no_show") is True
            visit.scheduling_method = payload.get("Metodo de programación")
            visit.revenue = Decimal(str(payload.get("_revenue") or 0)).quantize(Decimal("0.01"))
            visit.last_seen_import = report_import
            visit.source_raw_row = raw_row
            visit.save()
            stats["attendance_changed"] += 1

        if changes or not previous_snapshot:
            AttendanceVisitVersion.objects.create(
                attendance_visit=visit,
                report_import=report_import,
                raw_row=raw_row,
                row_hash=row["hash"],
                changed_fields=changes,
                snapshot=snapshot,
            )
            stats["versions_created"] += 1

    stats["natural_key_collisions"] = len(rows_to_import["valid_rows"]) - len(current_visit_candidates)

    for row in rows_to_import["invalid_rows"]:
        AttendanceRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=row["payload"],
            is_valid=False,
            validation_errors=row["errors"],
        )
        stats["raw_rows_created"] += 1

    report_import.status = ReportImport.STATUS_COMPLETED
    report_import.processed_at = timezone.now()
    report_import.save(update_fields=["status", "processed_at"])

    return {"preview": preview, "import": stats}


def preview_attendance_rows(uploaded_file):
    uploaded_file.seek(0)
    sheet_name, parsed_rows = load_first_sheet_rows(uploaded_file)
    headers, rows = table_from_rows(parsed_rows)

    valid_rows = []
    invalid_rows = []
    footer_rows = []
    for row in rows:
        if clean_value(row["payload"].get("Fecha")).casefold() in ("total", "totales"):
            footer_rows.append(row)
            continue

        raw_payload = dict(row["payload"])
        payload = {key: clean_value(value) for key, value in row["payload"].items()}
        errors = []
        visit_date = parse_excel_date(payload.get("Fecha"))
        expiration_date = parse_excel_date(payload.get("Fecha de Exp."))
        revenue = parse_number(payload.get("Ingresos por visita"))

        if not visit_date:
            errors.append("Invalid Fecha")
        if not payload.get("ID del cliente"):
            errors.append("Missing ID del cliente")
        if not payload.get("Cliente"):
            errors.append("Missing Cliente")
        if not payload.get("Ubicación de visita"):
            errors.append("Missing Ubicación de visita")
        if revenue is None:
            errors.append("Invalid Ingresos por visita")

        payload["_visit_date"] = visit_date.isoformat() if visit_date else None
        payload["_expiration_date"] = expiration_date.isoformat() if expiration_date else None
        payload["_staff_paid"] = parse_yes_no(payload.get("Personal pagado"))
        payload["_late_cancel"] = parse_yes_no(payload.get("Cancelación tardíá"))
        payload["_no_show"] = parse_yes_no(payload.get("No presentado"))
        payload["_revenue"] = revenue

        enriched = {
            "row_number": row["row_number"],
            "hash": row_hash(payload),
            "payload": payload,
            "raw_payload": raw_payload,
            "errors": errors,
        }
        if errors:
            invalid_rows.append(enriched)
        else:
            valid_rows.append(enriched)

    return {
        "sheet_name": sheet_name,
        "headers": headers,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "footer_rows": footer_rows,
    }


def validate_sales_rows(uploaded_file):
    uploaded_file.seek(0)
    sheet_name, parsed_rows = load_first_sheet_rows(uploaded_file)
    headers, rows = table_from_rows(parsed_rows)

    valid_rows = []
    invalid_rows = []
    footer_rows = []
    for row in rows:
        if clean_value(row["payload"].get("Fecha de Venta")).casefold() in ("total", "totales"):
            footer_rows.append(row)
            continue

        raw_payload = dict(row["payload"])
        payload = {key: clean_value(value) for key, value in row["payload"].items()}
        errors = []
        sale_date = parse_excel_date(payload.get("Fecha de Venta"))
        item_price = parse_number(payload.get("Precio del artículo (excluyendo impuestos)"))
        quantity = parse_number(payload.get("Cantidad"))
        subtotal = parse_number(payload.get("Sub-total (excluyendo impuestos)"))
        discount_percent = parse_number(payload.get("Descuento en %"))
        discount_amount = parse_number(payload.get("Cantidad de descuento"))
        tax = parse_number(payload.get("Impuesto"))
        item_total = parse_number(payload.get("Total de artículos"))
        paid_total = parse_number(payload.get("Total Pagado con Método de Pago"))

        if not sale_date:
            errors.append("Invalid Fecha de Venta")
        if not payload.get("ID del Cliente"):
            errors.append("Missing ID del Cliente")
        if not payload.get("Cliente"):
            errors.append("Missing Cliente")
        if not payload.get("No. de Venta"):
            errors.append("Missing No. de Venta")
        if not payload.get("Nombre del artículo"):
            errors.append("Missing Nombre del artículo")
        for label, value in (
            ("Precio del artículo (excluyendo impuestos)", item_price),
            ("Cantidad", quantity),
            ("Sub-total (excluyendo impuestos)", subtotal),
            ("Descuento en %", discount_percent),
            ("Cantidad de descuento", discount_amount),
            ("Impuesto", tax),
            ("Total de artículos", item_total),
            ("Total Pagado con Método de Pago", paid_total),
        ):
            if value is None:
                errors.append(f"Invalid {label}")

        payload["_sale_date"] = sale_date.isoformat() if sale_date else None
        payload["_item_price"] = item_price
        payload["_quantity"] = quantity
        payload["_subtotal"] = subtotal
        payload["_discount_percent"] = discount_percent
        payload["_discount_amount"] = discount_amount
        payload["_tax"] = tax
        payload["_item_total"] = item_total
        payload["_paid_total"] = paid_total

        enriched = {
            "row_number": row["row_number"],
            "hash": row_hash(payload),
            "payload": payload,
            "raw_payload": raw_payload,
            "errors": errors,
        }
        if errors:
            invalid_rows.append(enriched)
        else:
            valid_rows.append(enriched)

    return {
        "sheet_name": sheet_name,
        "headers": headers,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "footer_rows": footer_rows,
    }


def preview_sales_report(uploaded_file, site):
    rows = validate_sales_rows(uploaded_file)
    allowed_headers = SALES_REQUIRED_HEADERS + SALES_OPTIONAL_HEADERS
    missing_headers = [header for header in SALES_REQUIRED_HEADERS if header not in rows["headers"]]
    extra_headers = [header for header in rows["headers"] if header not in allowed_headers]
    hash_counts = Counter(row["hash"] for row in rows["valid_rows"])
    duplicate_groups = sum(1 for count in hash_counts.values() if count > 1)
    duplicate_extra_rows = sum(count - 1 for count in hash_counts.values() if count > 1)
    date_values = [
        parse_excel_date(row["payload"].get("Fecha de Venta"))
        for row in rows["valid_rows"]
        if parse_excel_date(row["payload"].get("Fecha de Venta"))
    ]
    sample_fields = [
        "Fecha de Venta",
        "ID del Cliente",
        "Cliente",
        "No. de Venta",
        "Nombre del artículo",
        "Localidad",
        "Forma de Pago",
        "Total de artículos",
    ]
    repeated_samples = repeated_row_samples(rows["valid_rows"], sample_fields)
    assign_occurrence_indexes(rows["valid_rows"], lambda payload: sale_natural_key(site, payload))

    return {
        "report_type": SALES_REPORT_TYPE,
        "sheet_name": rows["sheet_name"],
        "headers": rows["headers"],
        "missing_headers": missing_headers,
        "extra_headers": extra_headers,
        "is_valid_schema": not missing_headers,
        "row_counts": {
            "raw_rows": len(rows["valid_rows"]) + len(rows["invalid_rows"]) + len(rows["footer_rows"]),
            "data_rows": len(rows["valid_rows"]) + len(rows["invalid_rows"]),
            "footer_rows": len(rows["footer_rows"]),
            "valid_rows": len(rows["valid_rows"]),
            "invalid_rows": len(rows["invalid_rows"]),
            "duplicate_groups": duplicate_groups,
            "duplicate_extra_rows": duplicate_extra_rows,
        },
        "date_range": {
            "from": min(date_values).isoformat() if date_values else None,
            "to": max(date_values).isoformat() if date_values else None,
        },
        "sales": {
            "gross_item_total": round(sum(row["payload"]["_item_total"] for row in rows["valid_rows"]), 2),
            "paid_total": round(sum(row["payload"]["_paid_total"] for row in rows["valid_rows"]), 2),
            "discount_total": round(sum(row["payload"]["_discount_amount"] for row in rows["valid_rows"]), 2),
            "tax_total": round(sum(row["payload"]["_tax"] for row in rows["valid_rows"]), 2),
            "sale_count": len({row["payload"].get("No. de Venta") for row in rows["valid_rows"]}),
        },
        "revenue": {
            "total": round(sum(row["payload"]["_paid_total"] for row in rows["valid_rows"]), 2),
            "zero_revenue_rows": sum(row["payload"]["_paid_total"] == 0 for row in rows["valid_rows"]),
        },
        "lookup_preview": build_sales_lookup_preview(site, rows["valid_rows"]),
        "data_quality": {
            "requires_review": False,
            "repeated_row_samples": repeated_samples,
            "natural_key_collision_samples": natural_key_collision_samples(
                rows["valid_rows"],
                lambda payload: sale_natural_key(site, payload),
                sample_fields,
            ),
            "import_impact": current_record_impact(
                rows["valid_rows"],
                SaleLine,
                lambda payload: sale_natural_key(site, payload),
            ),
        },
        "invalid_row_samples": rows["invalid_rows"][:10],
        "sample_rows": rows["valid_rows"][:5],
    }


def sale_natural_key(site, payload):
    return hash_parts([
        site.id,
        payload.get("_occurrence_index"),
        payload.get("ID del Cliente"),
        payload.get("_sale_date"),
        payload.get("No. de Venta"),
        payload.get("Nombre del artículo"),
        payload.get("Computación #"),
        payload.get("Forma de Pago"),
        payload.get("_item_total"),
        payload.get("_paid_total"),
    ])


def sale_snapshot(payload, related):
    return {
        "site_id": related["site"].id,
        "client_id": related["client"].id,
        "studio_id": related["studio"].id if related["studio"] else None,
        "payment_method_id": related["payment_method"].id if related["payment_method"] else None,
        "occurrence_index": payload.get("_occurrence_index"),
        "sale_date": payload.get("_sale_date"),
        "sale_number": payload.get("No. de Venta"),
        "item_name": payload.get("Nombre del artículo"),
        "computation_number": payload.get("Computación #"),
        "sale_notes": payload.get("Notas de Venta"),
        "item_notes": payload.get("Notas"),
        "color": payload.get("Color"),
        "size": payload.get("Tamaño"),
        "item_price": decimal_string(payload.get("_item_price")),
        "quantity": decimal_string(payload.get("_quantity")),
        "subtotal": decimal_string(payload.get("_subtotal")),
        "discount_percent": decimal_string(payload.get("_discount_percent")),
        "discount_amount": decimal_string(payload.get("_discount_amount")),
        "tax": decimal_string(payload.get("_tax")),
        "item_total": decimal_string(payload.get("_item_total")),
        "paid_total": decimal_string(payload.get("_paid_total")),
    }


@transaction.atomic
def import_sales_report(uploaded_file, site, uploaded_by=None):
    preview = preview_sales_report(uploaded_file, site)
    if not preview["is_valid_schema"]:
        raise ValueError(f"Missing required headers: {', '.join(preview['missing_headers'])}")

    report_import = ReportImport.objects.create(
        report_type=SALES_REPORT_TYPE,
        source_system="mindbody",
        file_name=getattr(uploaded_file, "name", "uploaded.xlsx"),
        status=ReportImport.STATUS_PROCESSING,
        total_rows=preview["row_counts"]["data_rows"],
        valid_rows=preview["row_counts"]["valid_rows"],
        error_rows=preview["row_counts"]["invalid_rows"],
        uploaded_by=uploaded_by,
    )
    stats = {
        "report_import_id": report_import.id,
        "raw_rows_created": 0,
        "sale_lines_created": 0,
        "sale_lines_changed": 0,
        "sale_lines_identical": 0,
        "natural_key_collisions": 0,
        "versions_created": 0,
        "new_lookups": {"clients": 0, "studios": 0, "payment_methods": 0},
    }
    rows_to_import = validate_sales_rows(uploaded_file)
    assign_occurrence_indexes(rows_to_import["valid_rows"], lambda payload: sale_natural_key(site, payload))
    current_candidates = {}

    for row in rows_to_import["valid_rows"]:
        payload = row["payload"]
        client, created = get_or_create_scoped(Client, site, payload.get("Cliente"), mindbody_id=payload.get("ID del Cliente"))
        stats["new_lookups"]["clients"] += int(created)
        studio, created = get_or_create_scoped(Studio, site, payload.get("Localidad"))
        stats["new_lookups"]["studios"] += int(created)
        payment_method, created = get_or_create_scoped(PaymentMethod, site, payload.get("Forma de Pago"))
        stats["new_lookups"]["payment_methods"] += int(created)

        raw_row = SaleRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=payload,
            is_valid=True,
            validation_errors=[],
        )
        stats["raw_rows_created"] += 1
        related = {"site": site, "client": client, "studio": studio, "payment_method": payment_method}
        current_candidates[sale_natural_key(site, payload)] = {
            "row": row,
            "payload": payload,
            "raw_row": raw_row,
            "related": related,
        }

    for natural_key, candidate in current_candidates.items():
        row = candidate["row"]
        payload = candidate["payload"]
        raw_row = candidate["raw_row"]
        related = candidate["related"]
        snapshot = sale_snapshot(payload, related)
        sale_line = SaleLine.objects.filter(natural_key=natural_key).first()
        previous_snapshot = None
        if sale_line:
            previous_version = sale_line.versions.order_by("-created_at").first()
            previous_snapshot = previous_version.snapshot if previous_version else None

        changes = changed_fields(previous_snapshot, snapshot)
        values = {
            "site": site,
            "current_row_hash": row["hash"],
            "client": related["client"],
            "studio": related["studio"],
            "payment_method": related["payment_method"],
            "sale_date": payload["_sale_date"],
            "sale_number": payload.get("No. de Venta") or "",
            "item_name": payload.get("Nombre del artículo") or "",
            "computation_number": payload.get("Computación #"),
            "sale_notes": payload.get("Notas de Venta"),
            "item_notes": payload.get("Notas"),
            "color": payload.get("Color"),
            "size": payload.get("Tamaño"),
            "item_price": money(payload.get("_item_price")),
            "quantity": money(payload.get("_quantity")),
            "subtotal": money(payload.get("_subtotal")),
            "discount_percent": money(payload.get("_discount_percent")),
            "discount_amount": money(payload.get("_discount_amount")),
            "tax": money(payload.get("_tax")),
            "item_total": money(payload.get("_item_total")),
            "paid_total": money(payload.get("_paid_total")),
            "last_seen_import": report_import,
            "source_raw_row": raw_row,
        }

        if not sale_line:
            sale_line = SaleLine.objects.create(
                natural_key=natural_key,
                first_seen_import=report_import,
                **values,
            )
            stats["sale_lines_created"] += 1
            changes = list(snapshot.keys())
        elif sale_line.current_row_hash == row["hash"]:
            sale_line.last_seen_import = report_import
            sale_line.source_raw_row = raw_row
            sale_line.save(update_fields=["last_seen_import", "source_raw_row", "updated_at"])
            stats["sale_lines_identical"] += 1
        else:
            for field, value in values.items():
                setattr(sale_line, field, value)
            sale_line.save()
            stats["sale_lines_changed"] += 1

        if changes or not previous_snapshot:
            SaleLineVersion.objects.create(
                sale_line=sale_line,
                report_import=report_import,
                raw_row=raw_row,
                row_hash=row["hash"],
                changed_fields=changes,
                snapshot=snapshot,
            )
            stats["versions_created"] += 1

    stats["natural_key_collisions"] = len(rows_to_import["valid_rows"]) - len(current_candidates)

    for row in rows_to_import["invalid_rows"]:
        SaleRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=row["payload"],
            is_valid=False,
            validation_errors=row["errors"],
        )
        stats["raw_rows_created"] += 1

    report_import.status = ReportImport.STATUS_COMPLETED
    report_import.processed_at = timezone.now()
    report_import.save(update_fields=["status", "processed_at"])
    return {"preview": preview, "import": stats}


def validate_sales_by_service_rows(uploaded_file):
    uploaded_file.seek(0)
    sheet_name, parsed_rows = load_first_sheet_rows(uploaded_file)
    headers, rows = table_from_rows(parsed_rows)

    valid_rows = []
    invalid_rows = []
    footer_rows = []
    for row in rows:
        if clean_value(row["payload"].get("Nombre")).casefold() in ("total", "totales"):
            footer_rows.append(row)
            continue

        raw_payload = dict(row["payload"])
        payload = {key: clean_value(value) for key, value in row["payload"].items()}
        errors = []
        sale_date = parse_excel_date(payload.get("Fecha de Venta"))
        activation_date = parse_excel_date(payload.get("Fecha de activación"))
        expiration_date = parse_excel_date(payload.get("Fecha de Expiración"))
        activation_offset = parse_int(payload.get("Días de activación de compensación"))
        total_amount = parse_number(payload.get("Cantidad total"))
        cash_equivalent = parse_number(payload.get("Equivalente en efectivo"))
        non_cash_equivalent = parse_number(payload.get("No equivalente de efectivo"))
        quantity = parse_number(payload.get("Cantidad"))

        if not payload.get("Nombre"):
            errors.append("Missing Nombre")
        if not payload.get("ID del Cliente"):
            errors.append("Missing ID del Cliente")
        if not payload.get("Cliente"):
            errors.append("Missing Cliente")
        if not sale_date:
            errors.append("Invalid Fecha de Venta")
        for label, value in (
            ("Cantidad total", total_amount),
            ("Equivalente en efectivo", cash_equivalent),
            ("No equivalente de efectivo", non_cash_equivalent),
            ("Cantidad", quantity),
        ):
            if value is None:
                errors.append(f"Invalid {label}")

        payload["_sale_date"] = sale_date.isoformat() if sale_date else None
        payload["_activation_date"] = activation_date.isoformat() if activation_date else None
        payload["_expiration_date"] = expiration_date.isoformat() if expiration_date else None
        payload["_activation_offset_days"] = activation_offset
        payload["_total_amount"] = total_amount
        payload["_cash_equivalent"] = cash_equivalent
        payload["_non_cash_equivalent"] = non_cash_equivalent
        payload["_quantity"] = quantity

        enriched = {
            "row_number": row["row_number"],
            "hash": row_hash(payload),
            "payload": payload,
            "raw_payload": raw_payload,
            "errors": errors,
        }
        if errors:
            invalid_rows.append(enriched)
        else:
            valid_rows.append(enriched)

    return {
        "sheet_name": sheet_name,
        "headers": headers,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "footer_rows": footer_rows,
    }


def preview_sales_by_service_report(uploaded_file, site):
    rows = validate_sales_by_service_rows(uploaded_file)
    missing_headers = [header for header in SALES_BY_SERVICE_REQUIRED_HEADERS if header not in rows["headers"]]
    extra_headers = [header for header in rows["headers"] if header not in SALES_BY_SERVICE_REQUIRED_HEADERS]
    hash_counts = Counter(row["hash"] for row in rows["valid_rows"])
    duplicate_groups = sum(1 for count in hash_counts.values() if count > 1)
    duplicate_extra_rows = sum(count - 1 for count in hash_counts.values() if count > 1)
    sale_dates = [
        parse_excel_date(row["payload"].get("Fecha de Venta"))
        for row in rows["valid_rows"]
        if parse_excel_date(row["payload"].get("Fecha de Venta"))
    ]
    expiration_dates = [
        parse_excel_date(row["payload"].get("Fecha de Expiración"))
        for row in rows["valid_rows"]
        if parse_excel_date(row["payload"].get("Fecha de Expiración"))
    ]
    sample_fields = [
        "Nombre",
        "ID del Cliente",
        "Cliente",
        "Categoría",
        "Fecha de Venta",
        "Fecha de activación",
        "Fecha de Expiración",
        "Cantidad total",
    ]
    repeated_samples = repeated_row_samples(rows["valid_rows"], sample_fields)
    assign_occurrence_indexes(
        rows["valid_rows"],
        lambda payload: service_purchase_natural_key(site, payload),
    )

    return {
        "report_type": SALES_BY_SERVICE_REPORT_TYPE,
        "sheet_name": rows["sheet_name"],
        "headers": rows["headers"],
        "missing_headers": missing_headers,
        "extra_headers": extra_headers,
        "is_valid_schema": not missing_headers,
        "row_counts": {
            "raw_rows": len(rows["valid_rows"]) + len(rows["invalid_rows"]) + len(rows["footer_rows"]),
            "data_rows": len(rows["valid_rows"]) + len(rows["invalid_rows"]),
            "footer_rows": len(rows["footer_rows"]),
            "valid_rows": len(rows["valid_rows"]),
            "invalid_rows": len(rows["invalid_rows"]),
            "duplicate_groups": duplicate_groups,
            "duplicate_extra_rows": duplicate_extra_rows,
        },
        "date_range": {
            "from": min(sale_dates).isoformat() if sale_dates else None,
            "to": max(sale_dates).isoformat() if sale_dates else None,
        },
        "service_expiration_range": {
            "from": min(expiration_dates).isoformat() if expiration_dates else None,
            "to": max(expiration_dates).isoformat() if expiration_dates else None,
        },
        "services": {
            "purchase_count": len(rows["valid_rows"]),
            "total_amount": round(sum(row["payload"]["_total_amount"] for row in rows["valid_rows"]), 2),
            "cash_equivalent": round(sum(row["payload"]["_cash_equivalent"] for row in rows["valid_rows"]), 2),
            "non_cash_equivalent": round(sum(row["payload"]["_non_cash_equivalent"] for row in rows["valid_rows"]), 2),
            "quantity": round(sum(row["payload"]["_quantity"] for row in rows["valid_rows"]), 2),
        },
        "revenue": {
            "total": round(sum(row["payload"]["_total_amount"] for row in rows["valid_rows"]), 2),
            "zero_revenue_rows": sum(row["payload"]["_total_amount"] == 0 for row in rows["valid_rows"]),
        },
        "lookup_preview": build_service_purchase_lookup_preview(site, rows["valid_rows"]),
        "data_quality": {
            "requires_review": False,
            "repeated_row_samples": repeated_samples,
            "natural_key_collision_samples": natural_key_collision_samples(
                rows["valid_rows"],
                lambda payload: service_purchase_natural_key(site, payload),
                sample_fields,
            ),
            "import_impact": current_record_impact(
                rows["valid_rows"],
                ServicePurchase,
                lambda payload: service_purchase_natural_key(site, payload),
            ),
        },
        "invalid_row_samples": rows["invalid_rows"][:10],
        "sample_rows": rows["valid_rows"][:5],
    }


def service_purchase_natural_key(site, payload):
    return hash_parts([
        site.id,
        payload.get("_occurrence_index"),
        payload.get("ID del Cliente"),
        payload.get("Nombre"),
        payload.get("_sale_date"),
        payload.get("_activation_date"),
        payload.get("_expiration_date"),
        payload.get("_total_amount"),
        payload.get("_quantity"),
    ])


def service_purchase_snapshot(payload, related):
    return {
        "site_id": related["site"].id,
        "client_id": related["client"].id,
        "service_category_id": related["service_category"].id if related["service_category"] else None,
        "pricing_option_id": related["pricing_option"].id,
        "occurrence_index": payload.get("_occurrence_index"),
        "sale_date": payload.get("_sale_date"),
        "activation_date": payload.get("_activation_date"),
        "expiration_date": payload.get("_expiration_date"),
        "activation_offset_days": payload.get("_activation_offset_days"),
        "total_amount": decimal_string(payload.get("_total_amount")),
        "cash_equivalent": decimal_string(payload.get("_cash_equivalent")),
        "non_cash_equivalent": decimal_string(payload.get("_non_cash_equivalent")),
        "quantity": decimal_string(payload.get("_quantity")),
    }


@transaction.atomic
def import_sales_by_service_report(uploaded_file, site, uploaded_by=None):
    preview = preview_sales_by_service_report(uploaded_file, site)
    if not preview["is_valid_schema"]:
        raise ValueError(f"Missing required headers: {', '.join(preview['missing_headers'])}")

    report_import = ReportImport.objects.create(
        report_type=SALES_BY_SERVICE_REPORT_TYPE,
        source_system="mindbody",
        file_name=getattr(uploaded_file, "name", "uploaded.xlsx"),
        status=ReportImport.STATUS_PROCESSING,
        total_rows=preview["row_counts"]["data_rows"],
        valid_rows=preview["row_counts"]["valid_rows"],
        error_rows=preview["row_counts"]["invalid_rows"],
        uploaded_by=uploaded_by,
    )
    stats = {
        "report_import_id": report_import.id,
        "raw_rows_created": 0,
        "service_purchases_created": 0,
        "service_purchases_changed": 0,
        "service_purchases_identical": 0,
        "natural_key_collisions": 0,
        "versions_created": 0,
        "new_lookups": {"clients": 0, "service_categories": 0, "pricing_options": 0},
    }
    rows_to_import = validate_sales_by_service_rows(uploaded_file)
    assign_occurrence_indexes(
        rows_to_import["valid_rows"],
        lambda payload: service_purchase_natural_key(site, payload),
    )
    current_candidates = {}

    for row in rows_to_import["valid_rows"]:
        payload = row["payload"]
        client, created = get_or_create_scoped(
            Client,
            site,
            payload.get("Cliente"),
            mindbody_id=payload.get("ID del Cliente"),
            phone=payload.get("Teléfono particular"),
        )
        stats["new_lookups"]["clients"] += int(created)
        service_category, created = get_or_create_scoped(ServiceCategory, site, payload.get("Categoría"))
        stats["new_lookups"]["service_categories"] += int(created)
        pricing_option, created = get_or_create_scoped(
            PricingOption,
            site,
            payload.get("Nombre"),
            service_category=service_category,
        )
        stats["new_lookups"]["pricing_options"] += int(created)

        raw_row = ServicePurchaseRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=payload,
            is_valid=True,
            validation_errors=[],
        )
        stats["raw_rows_created"] += 1
        related = {
            "site": site,
            "client": client,
            "service_category": service_category,
            "pricing_option": pricing_option,
        }
        current_candidates[service_purchase_natural_key(site, payload)] = {
            "row": row,
            "payload": payload,
            "raw_row": raw_row,
            "related": related,
        }

    for natural_key, candidate in current_candidates.items():
        row = candidate["row"]
        payload = candidate["payload"]
        raw_row = candidate["raw_row"]
        related = candidate["related"]
        snapshot = service_purchase_snapshot(payload, related)
        service_purchase = ServicePurchase.objects.filter(natural_key=natural_key).first()
        previous_snapshot = None
        if service_purchase:
            previous_version = service_purchase.versions.order_by("-created_at").first()
            previous_snapshot = previous_version.snapshot if previous_version else None

        changes = changed_fields(previous_snapshot, snapshot)
        values = {
            "site": site,
            "current_row_hash": row["hash"],
            "client": related["client"],
            "service_category": related["service_category"],
            "pricing_option": related["pricing_option"],
            "sale_date": payload["_sale_date"],
            "activation_date": payload.get("_activation_date"),
            "expiration_date": payload.get("_expiration_date"),
            "activation_offset_days": payload.get("_activation_offset_days"),
            "total_amount": money(payload.get("_total_amount")),
            "cash_equivalent": money(payload.get("_cash_equivalent")),
            "non_cash_equivalent": money(payload.get("_non_cash_equivalent")),
            "quantity": money(payload.get("_quantity")),
            "last_seen_import": report_import,
            "source_raw_row": raw_row,
        }
        if not service_purchase:
            service_purchase = ServicePurchase.objects.create(
                natural_key=natural_key,
                first_seen_import=report_import,
                **values,
            )
            stats["service_purchases_created"] += 1
            changes = list(snapshot.keys())
        elif service_purchase.current_row_hash == row["hash"]:
            service_purchase.last_seen_import = report_import
            service_purchase.source_raw_row = raw_row
            service_purchase.save(update_fields=["last_seen_import", "source_raw_row", "updated_at"])
            stats["service_purchases_identical"] += 1
        else:
            for field, value in values.items():
                setattr(service_purchase, field, value)
            service_purchase.save()
            stats["service_purchases_changed"] += 1

        if changes or not previous_snapshot:
            ServicePurchaseVersion.objects.create(
                service_purchase=service_purchase,
                report_import=report_import,
                raw_row=raw_row,
                row_hash=row["hash"],
                changed_fields=changes,
                snapshot=snapshot,
            )
            stats["versions_created"] += 1

    stats["natural_key_collisions"] = len(rows_to_import["valid_rows"]) - len(current_candidates)

    for row in rows_to_import["invalid_rows"]:
        ServicePurchaseRawRow.objects.create(
            report_import=report_import,
            site=site,
            row_number=row["row_number"],
            row_hash=row["hash"],
            raw_payload=row["raw_payload"],
            normalized_payload=row["payload"],
            is_valid=False,
            validation_errors=row["errors"],
        )
        stats["raw_rows_created"] += 1

    report_import.status = ReportImport.STATUS_COMPLETED
    report_import.processed_at = timezone.now()
    report_import.save(update_fields=["status", "processed_at"])
    return {"preview": preview, "import": stats}


def preview_report(uploaded_file, site, report_type):
    if report_type == ATTENDANCE_REPORT_TYPE:
        return preview_attendance_report(uploaded_file, site)
    if report_type == SALES_REPORT_TYPE:
        return preview_sales_report(uploaded_file, site)
    if report_type == SALES_BY_SERVICE_REPORT_TYPE:
        return preview_sales_by_service_report(uploaded_file, site)
    raise ValueError(f"Unsupported report_type. Supported: {', '.join(SUPPORTED_REPORT_TYPES)}.")


def import_report(uploaded_file, site, report_type, uploaded_by=None):
    if report_type == ATTENDANCE_REPORT_TYPE:
        return import_attendance_report(uploaded_file, site, uploaded_by=uploaded_by)
    if report_type == SALES_REPORT_TYPE:
        return import_sales_report(uploaded_file, site, uploaded_by=uploaded_by)
    if report_type == SALES_BY_SERVICE_REPORT_TYPE:
        return import_sales_by_service_report(uploaded_file, site, uploaded_by=uploaded_by)
    raise ValueError(f"Unsupported report_type. Supported: {', '.join(SUPPORTED_REPORT_TYPES)}.")
