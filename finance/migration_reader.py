"""Read-only native DR workbook preview. Never evaluates formulas or posts money."""
import io
import posixpath
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree as ET
from .bank_readers import normalized

VERSION = 'dr-enriched-xlsx-v1'
MAX_BYTES = 5 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_PART_BYTES = 20 * 1024 * 1024
MAX_ROWS = 20000
MAX_SCAN_ROWS = 25000
MAX_CELLS = 300000
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
MAPPINGS = {
    'debitos': {'bank_date': 'Fecha', 'amount': 'Monto', 'reference': 'No. Referencia', 'serial': 'No. Serial',
        'manual_description': 'Concepto', 'legacy_reviewed': 'Conciliado', 'original_description': 'Descripción Original',
        'expense_period': 'Periodo', 'category': 'Categoria', 'subcategory': 'Sub-categoria', 'location': 'Ubicación', 'legacy_type': 'Tipo'},
    'ingresos': {'bank_date': 'Fecha', 'original_description': 'Descripción', 'amount': 'Monto', 'balance': 'Balance',
        'payment_method': 'Concepto', 'operation_date': 'Fecha_operacion', 'manual_description': 'Motivo',
        'terminal': 'Terminal', 'location': 'Ubicacion'},
}


def safe_xml(archive, name):
    part = archive.getinfo(name)
    if part.file_size > MAX_PART_BYTES:
        raise ValueError('workbook_limit')
    with archive.open(name) as source:
        content = source.read(MAX_PART_BYTES + 1)
    if len(content) > MAX_PART_BYTES:
        raise ValueError('workbook_limit')
    # Reject DTD/entity declarations, including encodings that could conceal them.
    if b'\x00' in content or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('unsupported_xml')
    return ET.fromstring(content)


def column_number(reference):
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', reference)
    if not match: raise ValueError('invalid_cell_reference')
    value = 0
    for letter in match[1]: value = value * 26 + ord(letter) - 64
    if value > 256: raise ValueError('workbook_limit')
    return value, int(match[2])


def cell_value(cell, strings):
    kind = cell.get('t', 'n'); value = cell.find('s:v', NS); formula = cell.find('s:f', NS)
    text = value.text if value is not None else None
    error = None
    if kind == 's':
        try:
            if not text or not text.isdecimal(): raise ValueError()
            resolved = strings[int(text)]
        except (IndexError, ValueError, TypeError): raise ValueError('invalid_shared_string')
    elif kind == 'inlineStr':
        resolved = ''.join(part.text or '' for part in cell.findall('.//s:t', NS))
    elif kind == 'b':
        if text not in ('0','1'): raise ValueError('invalid_boolean')
        resolved = text == '1'
    elif kind == 'e': resolved = None; error = 'formula_error' if formula is not None else 'cell_error'
    elif kind in ('str','d'): resolved = text or ''
    else: resolved = text
    if formula is not None and value is None: error = 'formula_cache_missing'
    if formula is not None and kind == 'n' and text is None: error = 'formula_cache_missing'
    return {'cell': cell.get('r'), 'type': kind, 'value': resolved, 'reported_value': text,
        'formula': ''.join(formula.itertext()) if formula is not None else None,
        'formula_attributes': dict(formula.attrib) if formula is not None else {}, 'issue': error}


def parse_date(cell, epoch1904):
    if not cell or cell['value'] in (None,'') or cell['issue']:
        raise ValueError('invalid_date')
    value = cell['value']
    if cell['type'] == 'n':
        try:
            serial = Decimal(value)
            if not serial.is_finite() or serial < 1 or serial > 200000 or (not epoch1904 and int(serial) == 60): raise ValueError()
            base = date(1904,1,1) if epoch1904 else date(1899,12,31) if serial < 60 else date(1899,12,30)
            return (base + timedelta(days=int(serial))).isoformat()
        except (InvalidOperation,ValueError,OverflowError): raise ValueError('invalid_date')
    for pattern in ('%Y-%m-%d','%d/%m/%Y','%Y-%m-%dT%H:%M:%S'):
        try: return datetime.strptime(str(value).strip(),pattern).date().isoformat()
        except ValueError: pass
    raise ValueError('invalid_date')


def parse_period(cell, epoch1904):
    if not cell or cell['value'] in (None,''): return None
    if cell['type'] in ('n','d'):
        return parse_date(cell,epoch1904)[:7]
    value = str(cell['value']).strip()
    for pattern in ('%Y-%m','%m/%Y','%d/%m/%Y','%Y-%m-%d'):
        try: return datetime.strptime(value,pattern).strftime('%Y-%m')
        except ValueError: pass
    raise ValueError('invalid_period')


def parse_money(cell, optional=False):
    if not cell or cell['value'] in (None,''):
        if optional: return None
        raise ValueError('invalid_amount')
    value = cell['value']
    if isinstance(value,bool) or cell['issue']: raise ValueError('invalid_amount')
    text = str(value).strip()
    if cell['type'] != 'n' and not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?',text):
        raise ValueError('invalid_amount')
    try:
        number = Decimal(text.replace(',',''))
        if not number.is_finite() or abs(number) >= Decimal('10000000000000000'): raise ValueError()
        rounded = number.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        # Excel can serialize binary floating-point noise. Preserve the original
        # text and normalize only sub-cent noise, never substantive precision.
        if abs(number-rounded) > Decimal('.00000001') or abs(rounded) >= Decimal('10000000000000000'): raise ValueError()
        return rounded
    except (InvalidOperation,ValueError): raise ValueError('invalid_amount')


def base_totals(rows):
    valid = [row for row in rows if row['bank_date'] and row['amount'] is not None]
    credits = sum((Decimal(row['amount']) for row in valid if row['kind']=='credit'),Decimal(0))
    debits = -sum((Decimal(row['amount']) for row in valid if row['kind']=='debit'),Decimal(0))
    return {'rows':len(rows),'valid_amount_date_rows':len(valid),'review_rows':sum(bool(row['issues']) for row in rows),
        'credit_total':f'{credits:.2f}','debit_total':f'{debits:.2f}','net_amount':f'{credits-debits:.2f}'}


def totals(rows):
    result = base_totals(rows)
    result['by_kind'] = {kind:base_totals([row for row in rows if row['kind']==kind]) for kind in ('debit','credit')}
    return result


def read_migration_xlsx(content, selected_month):
    result = {'parser_version':VERSION,'rows':[],'file_issues':[],'sheets':[],'summary':{},'mappings':{}}
    try:
        if len(content)>MAX_BYTES:raise ValueError('file_too_large')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos)>2000 or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>MAX_EXPANDED_BYTES:
                raise ValueError('workbook_limit')
            if any('vbaproject' in item.filename.casefold() for item in infos):raise ValueError('unsupported_macros')
            workbook = safe_xml(archive,'xl/workbook.xml')
            properties = workbook.find('s:workbookPr',NS)
            epoch1904 = properties is not None and properties.get('date1904') in ('1','true')
            relations = safe_xml(archive,'xl/_rels/workbook.xml.rels')
            paths = {item.get('Id'):item.get('Target') for item in relations if item.get('TargetMode')!='External'}
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(t.text or '' for t in item.findall('.//s:t',NS)) for item in safe_xml(archive,'xl/sharedStrings.xml')]
            found = set(); used_paths = set(); cell_count = 0; skipped = 0
            for sheet in workbook.findall('s:sheets/s:sheet',NS):
                name = sheet.get('name',''); key = normalized(name)
                if len(name)>31:raise ValueError('invalid_workbook')
                result['sheets'].append({'name':name,'movement_sheet':key in MAPPINGS})
                if key not in MAPPINGS:continue
                if key in found:raise ValueError('ambiguous_movement_sheets')
                found.add(key)
                target = paths.get(sheet.get(REL),'')
                path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target))
                if not path.startswith('xl/') or '..' in path.split('/'):raise ValueError('invalid_workbook_path')
                if path in used_paths:raise ValueError('invalid_workbook')
                used_paths.add(path)
                data = safe_xml(archive,path); headers = None; mapping = {}
                previous_row = 0
                for row in data.findall('s:sheetData/s:row',NS):
                    row_number = int(row.get('r','0'))
                    if row_number<=previous_row or row_number>MAX_SCAN_ROWS:raise ValueError('workbook_limit')
                    previous_row = row_number; cells = {}
                    for item in row.findall('s:c',NS):
                        column, source_row = column_number(item.get('r',''))
                        if source_row!=row_number or column in cells:raise ValueError('invalid_cell_reference')
                        cell_count += 1
                        if cell_count>MAX_CELLS:raise ValueError('workbook_limit')
                        cells[column] = cell_value(item,strings)
                    if row_number==1:
                        headers = {column:normalized(str(cell['value'] or '')) for column,cell in cells.items()}
                        for field,label in MAPPINGS[key].items():
                            columns = [column for column,value in headers.items() if value==normalized(label)]
                            if len(columns)>1:raise ValueError('duplicate_header')
                            if columns:mapping[field] = columns[0]
                        if not {'bank_date','amount','original_description','manual_description'} <= set(mapping):raise ValueError('missing_header')
                        result['mappings'][name] = {field:cells[column]['value'] for field,column in mapping.items()}
                        continue
                    if headers is None:raise ValueError('missing_header')
                    mapped = {field:cells.get(column) for field,column in mapping.items()}
                    # Workbook checkboxes are prefilled far beyond real data.
                    if not any(cell and cell['value'] not in (None,'') or cell and cell['issue'] for field,cell in mapped.items() if field!='legacy_reviewed'):
                        skipped += 1;continue
                    if len(result['rows'])>=MAX_ROWS:raise ValueError('workbook_limit')
                    kind = 'debit' if key=='debitos' else 'credit'
                    parsed = {'payment_origin':'unknown','currency':'DOP'}; issues = [{'code':'payment_origin_unknown','field':'payment_origin'}]
                    for field,cell in mapped.items():
                        if cell and cell['issue']:issues.append({'code':cell['issue'],'field':field})
                    bank_date = None; amount = None; operation_date = None; expense_period = None
                    try:bank_date=parse_date(mapped.get('bank_date'),epoch1904)
                    except ValueError as error:issues.append({'code':str(error),'field':'bank_date'})
                    try:
                        number=parse_money(mapped.get('amount'))
                        if number==0:raise ValueError('zero_amount')
                        if kind=='credit' and number<0:raise ValueError('negative_income_amount')
                        amount=f'{-abs(number) if kind=="debit" else number:.2f}'
                    except ValueError as error:issues.append({'code':str(error),'field':'amount'})
                    if mapped.get('operation_date') and mapped['operation_date']['value'] not in (None,''):
                        try:operation_date=parse_date(mapped['operation_date'],epoch1904)
                        except ValueError:issues.append({'code':'invalid_date','field':'operation_date'})
                    try:expense_period=parse_period(mapped.get('expense_period'),epoch1904)
                    except ValueError as error:issues.append({'code':str(error),'field':'expense_period'})
                    if kind=='debit' and not expense_period:issues.append({'code':'expense_period_missing','field':'expense_period'})
                    if kind=='credit' and not operation_date:issues.append({'code':'operation_date_missing','field':'operation_date'})
                    try:
                        balance=parse_money(mapped.get('balance'),optional=True)
                        parsed['balance']=f'{balance:.2f}' if balance is not None else None
                    except ValueError:parsed['balance']=None;issues.append({'code':'invalid_amount','field':'balance'})
                    for field in ('original_description','manual_description','reference','serial','category','subcategory','location','payment_method','terminal','legacy_type'):
                        cell=mapped.get(field); value=cell['value'] if cell else None
                        parsed[field]=str(value).strip() if value not in (None,'') else None
                        if field in ('category','subcategory') and cell and cell['type']=='n' and value not in (None,''):
                            issues.append({'code':'invalid_label','field':field})
                    reviewed=mapped.get('legacy_reviewed');parsed['legacy_reviewed']=reviewed['value'] if reviewed else None
                    if reviewed and reviewed['value'] not in (None,'') and not isinstance(reviewed['value'],bool):
                        issues.append({'code':'review_flag_unrecognized','field':'legacy_reviewed'})
                    if not parsed['location']:issues.append({'code':'location_missing','field':'location'})
                    parsed.update(bank_date=bank_date,amount=amount,operation_date=operation_date,expense_period=expense_period)
                    result['rows'].append({'sheet':name,'source_row':row_number,'kind':kind,'bank_date':bank_date,
                        'operation_date':operation_date,'expense_period':expense_period+'-01' if expense_period else None,
                        'amount':amount,'raw':list(cells.values()),'parsed':parsed,'issues':issues})
            if found!=set(MAPPINGS):raise ValueError('missing_movement_sheet')
            result['summary']['ignored_empty_rows']=skipped
    except (zipfile.BadZipFile,KeyError,ET.ParseError,ValueError,RuntimeError,NotImplementedError,OverflowError) as error:
        known={'file_too_large','workbook_limit','unsupported_macros','unsupported_xml','invalid_shared_string','invalid_boolean',
            'ambiguous_movement_sheets','invalid_workbook_path','invalid_cell_reference','duplicate_header','missing_header','missing_movement_sheet'}
        result['file_issues'].append(str(error) if str(error) in known else 'invalid_workbook')
    rows=result['rows'];result['summary'].update(currency='DOP',selected_month=selected_month,financial_records_created=0,
        all_rows=totals(rows),selected_bank_month=totals([row for row in rows if (row['bank_date'] or '').startswith(selected_month)]),
        unresolved_payment_origins=len(rows),
        first_bank_date=min((r['bank_date'] for r in rows if r['bank_date']),default=None),
        last_bank_date=max((r['bank_date'] for r in rows if r['bank_date']),default=None))
    for field in ('bank_date','operation_date','expense_period'):
        groups=defaultdict(list)
        for row in rows:
            if row[field]:groups[row[field][:7]].append(row)
        result['summary'][field+'_months']={period:totals(groups[period]) for period in sorted(groups)}
    if not rows and not result['file_issues']:result['file_issues'].append('no_movements')
    if result['file_issues']:result['summary']['totals_are_partial']=True
    return result
