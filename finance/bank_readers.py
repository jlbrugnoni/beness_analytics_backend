"""Versioned, read-only CSV readers. Never identifies or creates movements."""
import csv
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

PARSER_VERSION = 'bank-csv-v1'
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
HEADERS = {
    'popular': ['Fecha Posteo', 'Descripción Corta', 'Monto Transacción', 'Balance', 'No. Referencia', 'No. Serial', 'Descripción'],
    'caixa': ['Concepto', 'Fecha', 'Importe', 'Saldo'],
}


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).casefold().split())


def money(value, currency, required=True):
    value = value.strip()
    if not value and not required:
        return None
    if currency == 'EUR' and value.endswith('EUR'):
        value = value[:-3].strip()
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
        raise ValueError('invalid_amount')
    try:
        number = Decimal(value.replace(',', ''))
    except InvalidOperation:
        raise ValueError('invalid_amount')
    if abs(number) >= Decimal('10000000000000000'):
        raise ValueError('amount_out_of_range')
    return f'{number:.2f}'


def read_bank_csv(content, provider):
    currency = 'DOP' if provider == 'popular' else 'EUR'
    output = {'parser_version': PARSER_VERSION, 'encoding': '', 'rows': [], 'file_issues': [], 'summary': {}}
    if b'\x00' in content:
        output['file_issues'].append('binary_or_unsupported_encoding')
    else:
        try:
            text = content.decode('utf-8-sig')
            output['encoding'] = 'utf-8-sig'
        except UnicodeDecodeError:
            try:
                text = content.decode('cp1252')
                output['encoding'] = 'cp1252'
            except UnicodeDecodeError:
                output['file_issues'].append('unsupported_encoding')
        if not output['file_issues']:
            expected = {normalized(name) for name in HEADERS[provider]}
            header = None
            section = 0
            previous_line = 0
            reader = csv.reader(io.StringIO(text, newline=''), delimiter=',' if provider == 'popular' else ';', strict=True)
            try:
                for index, raw in enumerate(reader, 1):
                    if index > MAX_ROWS:
                        output['file_issues'].append('too_many_rows')
                        break
                    row = {'row_number': index, 'source_line': previous_line + 1, 'source_line_end': reader.line_num,
                           'section': section, 'kind': 'preamble', 'raw': raw, 'parsed': {}, 'issues': []}
                    previous_line = reader.line_num
                    names = [normalized(value) for value in raw]
                    if not any(value.strip() for value in raw):
                        row['kind'] = 'blank'
                    elif expected <= set(names) and len(names) == len(set(names)):
                        header = {name: i for i, name in enumerate(names)}
                        section += 1
                        row.update(kind='header', section=section)
                    elif header is not None:
                        row['kind'] = 'data'
                        try:
                            if len(raw) != len(header):
                                raise ValueError('column_count')
                            get = lambda name: raw[header[normalized(name)]]
                            date = datetime.strptime(get('Fecha Posteo' if provider == 'popular' else 'Fecha').strip(), '%d/%m/%Y').date()
                            amount = Decimal(money(get('Monto Transacción' if provider == 'popular' else 'Importe'), currency))
                            if provider == 'popular':
                                direction = normalized(get('Descripción Corta'))
                                if amount < 0:
                                    raise ValueError('unexpected_amount_sign')
                                if direction.startswith('credito'):
                                    pass
                                elif direction.startswith('debito') or direction.startswith('db '):
                                    amount = -amount
                                else:
                                    raise ValueError('unknown_direction')
                            if not amount:
                                raise ValueError('zero_amount')
                            balance = money(get('Balance' if provider == 'popular' else 'Saldo'), currency, required=False)
                            row['parsed'] = {'bank_date': date.isoformat(), 'amount': f'{amount:.2f}', 'balance': balance,
                                'currency': currency, 'direction': 'credit' if amount > 0 else 'debit',
                                'description': get('Descripción' if provider == 'popular' else 'Concepto'),
                                'short_description': get('Descripción Corta') if provider == 'popular' else '',
                                'reference': get('No. Referencia') if provider == 'popular' else '',
                                'serial': get('No. Serial') if provider == 'popular' else ''}
                        except (ValueError, IndexError) as error:
                            code = str(error)
                            row['issues'].append(code if code in {'invalid_amount', 'amount_out_of_range', 'column_count', 'zero_amount',
                                'unexpected_amount_sign', 'unknown_direction'} else 'invalid_date')
                    output['rows'].append(row)
            except csv.Error:
                output['file_issues'].append('invalid_csv')
            if header is None:
                output['file_issues'].append('missing_header')
    valid = [r['parsed'] for r in output['rows'] if r['kind'] == 'data' and not r['issues']]
    invalid = sum(r['kind'] == 'data' and bool(r['issues']) for r in output['rows'])
    credits = [Decimal(r['amount']) for r in valid if r['direction'] == 'credit']
    debits = [-Decimal(r['amount']) for r in valid if r['direction'] == 'debit']
    dates = sorted(r['bank_date'] for r in valid)
    # Occurrences are counted, never collapsed; this is not transaction identity.
    repeats = Counter((r['bank_date'], r['description'], r['amount'], r['balance'], r['reference'], r['serial'], r['short_description']) for r in valid)
    if not valid and not invalid and not output['file_issues']:
        output['file_issues'].append('no_transactions')
    output['summary'] = {'currency': currency, 'valid_rows': len(valid), 'invalid_rows': invalid,
        'credit_count': len(credits), 'debit_count': len(debits),
        'credit_total': f'{sum(credits, Decimal(0)):.2f}', 'debit_total': f'{sum(debits, Decimal(0)):.2f}',
        'net_total': f'{sum(credits, Decimal(0)) - sum(debits, Decimal(0)):.2f}',
        'first_bank_date': dates[0] if dates else None, 'last_bank_date': dates[-1] if dates else None,
        'repeated_occurrences': sum(count - 1 for count in repeats.values() if count > 1),
        'header_sections': sum(r['kind'] == 'header' for r in output['rows']), 'financial_records_created': 0}
    return output
