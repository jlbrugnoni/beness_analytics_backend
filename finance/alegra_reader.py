"""Read-only Dominican Alegra item export. Source previews never post sales."""
import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .bank_readers import MAX_FILE_BYTES, MAX_ROWS, normalized, money

PARSER_VERSION = 'alegra-items-v2'
FIELDS = {
    'date': 'FECHA DE EMISIÓN', 'code': 'CÓDIGO', 'status': 'ESTADO',
    'cost_center': 'CENTRO DE COSTO', 'payment_method': 'MÉTODO DE PAGO', 'price_list': 'LISTAS DE PRECIOS',
    'customer': 'CLIENTE - NOMBRE', 'item_name': 'PRODUCTO/SERVICIO - NOMBRE',
    'quantity': 'PRODUCTO/SERVICIO - CANTIDAD', 'unit_price': 'PRODUCTO/SERVICIO - PRECIO UNITARIO',
    'item_total': 'PRODUCTO/SERVICIO - TOTAL', 'invoice_total': 'TOTAL - FACTURA',
}
HEADER_KEYS = ('date', 'code', 'status', 'cost_center', 'payment_method', 'price_list', 'customer', 'invoice_total')


def number(value):
    if not re.fullmatch(r'\d+(?:\.\d{1,6})?', value.strip()):
        raise ValueError('invalid_quantity_or_price')
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        raise ValueError('invalid_quantity_or_price')
    if result >= Decimal('10000000000000000'):
        raise ValueError('amount_out_of_range')
    return str(result)


def read_alegra_csv(content):
    result = dict(parser_version=PARSER_VERSION, encoding='', rows=[], invoices=[], file_issues=[], summary={})
    text = ''
    if len(content) > MAX_FILE_BYTES:
        result['file_issues'].append('file_too_large')
    elif b'\x00' in content:
        result['file_issues'].append('binary_or_unsupported_encoding')
    else:
        for encoding in ('utf-8-sig', 'cp1252'):
            try:
                text = content.decode(encoding); result['encoding'] = encoding
                break
            except UnicodeDecodeError:
                continue
        else:
            result['file_issues'].append('unsupported_encoding')
    header = None
    groups = defaultdict(list)
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=';', strict=True)
    previous = 0
    try:
        for index, raw in enumerate(reader, 1):
            if index > MAX_ROWS:
                result['file_issues'].append('too_many_rows'); break
            row = dict(row_number=index, source_line=previous + 1, source_line_end=reader.line_num,
                       kind='preamble', raw=raw, parsed={}, issues=[])
            previous = reader.line_num
            names = [normalized(value) for value in raw]
            required = [normalized(value) for value in FIELDS.values()]
            if not any(value.strip() for value in raw):
                row['kind'] = 'blank'
            elif set(required) <= set(names):
                row['kind'] = 'header'
                # Repeated tax column names are legitimate. Required identity/value
                # columns must occur exactly once, never silently select the first.
                if any(names.count(name) != 1 for name in required):
                    result['file_issues'].append('duplicate_required_header')
                    header = None
                else:
                    header = {key: names.index(normalized(value)) for key, value in FIELDS.items()}
                    header['_width'] = len(raw)
            elif header is not None:
                row['kind'] = 'data'
                get = lambda key: raw[header[key]].strip() if header[key] < len(raw) else ''
                parsed = {key: get(key) for key in FIELDS}
                row['parsed'] = parsed
                if len(raw) != header['_width']:
                    row['issues'].append('column_count')
                if not parsed['code']:
                    row['issues'].append('missing_invoice_code')
                elif not re.fullmatch(r'B0[12]\d{8}', parsed['code']):
                    row['issues'].append('unexpected_invoice_code')
                try:
                    parsed['date'] = datetime.strptime(parsed['date'], '%d/%m/%Y').date().isoformat()
                except ValueError:
                    row['issues'].append('invalid_date')
                for key in ('item_total', 'invoice_total'):
                    try:
                        parsed[key] = money(parsed[key], 'DOP')
                        if Decimal(parsed[key]) < 0:
                            raise ValueError('negative_invoice_amount')
                    except ValueError as error:
                        row['issues'].append(str(error))
                for key in ('quantity', 'unit_price'):
                    try:
                        parsed[key] = number(parsed[key])
                    except ValueError as error:
                        row['issues'].append(str(error))
                if not parsed['item_name']:
                    row['issues'].append('missing_item_name')
                # Client-confirmed aliases; all other statuses stay unresolved.
                parsed['status_kind'] = {'cobrada': 'paid', 'anulada': 'cancelled'}.get(normalized(parsed['status']), 'review')
                if parsed['status_kind'] == 'review':
                    row['issues'].append('status_requires_review')
                groups[parsed['code'] or f'@missing:{index}'].append(row)
            result['rows'].append(row)
    except csv.Error:
        result['file_issues'].append('invalid_csv')
    if not any(row['kind'] == 'header' for row in result['rows']):
        result['file_issues'].append('missing_header')
    if not groups and not result['file_issues']:
        result['file_issues'].append('no_invoices')
    for occurrence, rows in enumerate(groups.values(), 1):
        source = {key: rows[0]['parsed'][key] for key in HEADER_KEYS}
        source['status_kind'] = rows[0]['parsed']['status_kind']
        issues = list(dict.fromkeys(issue for row in rows for issue in row['issues']))
        for key in HEADER_KEYS:
            if len({row['parsed'][key] for row in rows}) != 1:
                issues.append('inconsistent_' + key)
        # Unknown status is reviewable evidence, not a fabricated paid sale.
        valid_money = not any(issue in issues for issue in ('invalid_amount', 'amount_out_of_range', 'negative_invoice_amount'))
        item_sum = sum((Decimal(row['parsed']['item_total']) for row in rows), Decimal(0)) if valid_money else None
        source['item_sum'] = f'{item_sum:.2f}' if item_sum is not None else None
        if item_sum is not None and item_sum != Decimal(source['invoice_total']):
            issues.append('invoice_total_mismatch')
        result['invoices'].append(dict(occurrence=occurrence, code=source['code'], source=source,
            item_count=len(rows), row_numbers=[row['row_number'] for row in rows], issues=issues))
    eligible = [invoice for invoice in result['invoices'] if not invoice['issues']]
    paid = [invoice for invoice in eligible if invoice['source']['status_kind'] == 'paid']
    cancelled = [invoice for invoice in eligible if invoice['source']['status_kind'] == 'cancelled']
    dates = sorted(invoice['source']['date'] for invoice in eligible)
    result['summary'] = dict(currency='DOP', item_rows=sum(len(rows) for rows in groups.values()),
        invoice_count=len(groups), valid_invoices=len(paid), cancelled_invoices=len(cancelled), review_invoices=len(groups) - len(eligible),
        paid_total=f"{sum((Decimal(invoice['source']['invoice_total']) for invoice in paid), Decimal(0)):.2f}",
        first_date=dates[0] if dates else None, last_date=dates[-1] if dates else None,
        financial_records_created=0)
    # A malformed/truncated file can retain evidence, but its partial totals must
    # never be presented as an eligible import.
    if result['file_issues']:
        result['summary']['valid_invoices'] = 0
        result['summary']['cancelled_invoices'] = 0
        result['summary']['review_invoices'] = len(groups)
        result['summary']['paid_total'] = None
    return result
