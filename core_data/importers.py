import datetime
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

from .models import Client, PaymentMethod, PricingOption, ServiceCategory, StaffMember, Studio


SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

ATTENDANCE_REPORT_TYPE = "attendance_with_revenue"

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


def clean_value(value):
    return str(value if value is not None else "").replace("\xa0", " ").strip()


def normalize_name(value):
    return clean_value(value).casefold()


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
        "invalid_row_samples": invalid_rows[:10],
        "sample_rows": valid_rows[:5],
    }
