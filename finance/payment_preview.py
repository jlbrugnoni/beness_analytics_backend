"""Derived payment evidence from an immutable workbook; no financial writes."""
import io
import posixpath
import re
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal
from xml.etree import ElementTree as ET
from .bank_readers import normalized
from .migration_reader import (NS, REL, MAX_BYTES, MAX_EXPANDED_BYTES, MAX_ROWS,
    MAX_SCAN_ROWS, MAX_CELLS, safe_xml, column_number, cell_value, parse_date, parse_money)

VERSION = 'alegra-workbook-payments-v1'
FIELDS = {'account':'Cuenta','date':'Fecha','number':'Numero','customer':'Cliente',
    'customer_id':'ID','amount':'Valor','observations':'Observaciones','notes':'Notas',
    'associations':'Asociaciones','kind':'Tipo_nota','source_reviewed':'Conciliada',
    'original_method':'Metodo_pago','status':'Estado','method':'Metodo',
    'manual_reviewed':'Conciliado','location':'Ubicación','cached_invoice':'NCF','currency':'Moneda'}
REQUIRED = {'date','number','amount','associations','kind','original_method'}
CODE = re.compile(r'(?<![A-Za-z0-9])B0[12]\d{8}(?![A-Za-z0-9])', re.I)
METHODS = {'cierre','link','recurrente','transferencia','efectivo'}


# Verified native transaction-export labels. Keep the enriched migration preset
# separate: punctuation/spacing changes are aliases, not guessed field semantics.
NATIVE_ALIASES = {'customer_id': {'RNC o Cédula'}, 'kind': {'Tipo de nota débito'},
    'source_reviewed': {'Conciliada?'}, 'original_method': {'Método de pago'}}


def header_names(key, native=False):
    labels = {FIELDS[key]}
    if key == 'currency': labels.add('Currency')
    if native: labels.update(NATIVE_ALIASES.get(key, set()))
    return {normalized(label) for label in labels}


def worksheet(content, report_sheet=False):
    if len(content)>MAX_BYTES: raise ValueError('file_too_large')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos=archive.infolist()
        if len(infos)>2000 or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>MAX_EXPANDED_BYTES:
            raise ValueError('workbook_limit')
        if any('vbaproject' in i.filename.casefold() for i in infos):raise ValueError('unsupported_macros')
        book=safe_xml(archive,'xl/workbook.xml');props=book.find('s:workbookPr',NS)
        epoch=props is not None and props.get('date1904') in ('1','true')
        all_sheets=book.findall('s:sheets/s:sheet',NS)
        relations=safe_xml(archive,'xl/_rels/workbook.xml.rels')
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(t.text or '' for t in s.findall('.//s:t',NS)) for s in safe_xml(archive,'xl/sharedStrings.xml')]
        def load(sheet):
            targets=[r.get('Target','') for r in relations if r.get('Id')==sheet.get(REL) and r.get('TargetMode')!='External']
            if len(targets)!=1:raise ValueError('invalid_workbook_path')
            target=targets[0];path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target))
            if not path.startswith('xl/') or '..' in path.split('/'):raise ValueError('invalid_workbook_path')
            return safe_xml(archive,path)
        scanned=0
        if report_sheet:
            if len(all_sheets)>100:raise ValueError('workbook_limit')
            candidates=[]
            required={k:header_names(k, native=True) for k in REQUIRED}
            for candidate in all_sheets:
                data=load(candidate)
                for node in data.findall('s:sheetData/s:row',NS):
                    number=int(node.get('r','0'))
                    if number>25:break
                    values=[]
                    for item in node.findall('s:c',NS):
                        scanned+=1
                        if scanned>MAX_CELLS:raise ValueError('workbook_limit')
                        value=cell_value(item,strings)['value']
                        values.append(normalized(str(value or '')))
                    if all(names.intersection(values) for names in required.values()):candidates.append((candidate,data,number))
            if not candidates:raise ValueError('missing_payment_header')
            if len(candidates)!=1:raise ValueError('ambiguous_payment_sheets')
            selected,sheet,header_number=candidates[0]
        else:
            sheets=[s for s in all_sheets if normalized(s.get('name',''))=='alegra_adm']
            if not sheets:raise ValueError('missing_payment_sheet')
            if len(sheets)!=1:raise ValueError('ambiguous_payment_sheets')
            selected=sheets[0];sheet=load(selected);header_number=1
        rows=[];previous=0;count=scanned;headers=None
        for node in sheet.findall('s:sheetData/s:row',NS):
            number=int(node.get('r','0'))
            if number<=previous or number>MAX_SCAN_ROWS:raise ValueError('workbook_limit')
            previous=number;cells={}
            for item in node.findall('s:c',NS):
                column,source_row=column_number(item.get('r',''))
                if source_row!=number or column in cells:raise ValueError('invalid_cell_reference')
                count+=1
                if count>MAX_CELLS:raise ValueError('workbook_limit')
                cells[column]=cell_value(item,strings)
            if number==header_number:headers=cells
            elif number>header_number:rows.append((number,cells))
        if headers is None:raise ValueError('missing_payment_header')
        mapping={}
        for key,label in FIELDS.items():
            columns=[c for c,v in headers.items() if normalized(str(v['value'] or '')) in header_names(key, native=report_sheet)]
            if len(columns)>1:raise ValueError('duplicate_header')
            if columns:mapping[key]=columns[0]
        if not REQUIRED<=mapping.keys():raise ValueError('missing_payment_header')
        return selected.get('name'),epoch,headers,mapping,rows


def text(cell):
    if not cell or cell['issue'] or cell['value'] in (None,''):return None
    return str(cell['value']).strip() or None


def payment_totals(rows):
    usable=[r for r in rows if r['date'] and r['amount'] is not None and r['kind']=='ingreso']
    return {'rows':len(rows),'review_rows':sum(bool(r['issues']) for r in rows),
        'valid_amount_date_rows':len(usable),
        'amount_total':f"{sum((Decimal(r['amount']) for r in usable),Decimal(0)):.2f}",
        'missing_numbers':sum(not r['number'] for r in rows),
        'split_invoice_groups':sum(n>1 for n in Counter(r['invoice_code'] for r in rows if r['invoice_code']).values())}


def read_payment_preview(content, prepared=None, report_sheet=False):
    result={'parser_version':VERSION,'rows':[],'file_issues':[],'summary':{}}
    try:
        name,epoch,headers,mapping,source=prepared if prepared is not None else worksheet(content, report_sheet=report_sheet)
        ignored=0
        for number,cells in source:
            mapped={key:cells.get(column) for key,column in mapping.items()}
            core=('account','date','number','amount','associations','original_method','kind')
            if not any(mapped.get(k) and (mapped[k]['value'] not in (None,'') or mapped[k]['issue']) for k in core):
                ignored+=1;continue
            if len(result['rows'])>=MAX_ROWS:raise ValueError('workbook_limit')
            row={key:text(mapped.get(key)) for key in FIELDS};row.update(sheet=name,source_row=number,issues=[],cells=[])
            issues=row['issues'];row['date']=None;row['amount']=None
            row['currency']=(row.get('currency') or 'DOP').upper()
            if row['currency']!='DOP':issues.append({'code':'currency_review','field':'currency'})
            for key,cell in mapped.items():
                if cell and cell['issue']:issues.append({'code':cell['issue'],'field':key})
            try:row['date']=parse_date(mapped.get('date'),epoch)
            except ValueError:issues.append({'code':'invalid_date','field':'date'})
            try:
                amount=parse_money(mapped.get('amount'))
                if amount<=0:raise ValueError()
                row['amount']=f'{amount:.2f}'
            except ValueError:issues.append({'code':'invalid_amount','field':'amount'})
            cell=mapped.get('number')
            if not row['number']:issues.append({'code':'missing_payment_number','field':'number'})
            elif len(row['number'])>64 or not re.fullmatch(r'[0-9]+',row['number']) or (cell and cell['type']=='b'):
                issues.append({'code':'invalid_payment_number','field':'number'})
            if row.get('status'):issues.append({'code':'payment_status_review','field':'status'})
            row['kind']=normalized(row['kind'] or '')
            if row['kind']!='ingreso':issues.append({'code':'unsupported_payment_kind','field':'kind'})
            references=list(dict.fromkeys(c.upper() for c in CODE.findall(row['associations'] or '')))
            # Only the observed single-invoice format is supported; unrecognized
            # trailing references must not be silently dropped by a regex match.
            association=row['associations'] or ''
            exact=re.fullmatch(r'\s*Facturas?\s*:\s*(B0[12]\d{8})\s*',association,re.I)
            row['invoice_code']=references[0] if len(references)==1 and exact else None
            if not row['invoice_code']:issues.append({'code':'invoice_reference_review','field':'associations'})
            cached=row['cached_invoice']
            if cached and cached.upper()!=row['invoice_code']:issues.append({'code':'invoice_reference_conflict','field':'cached_invoice'})
            row['method_origin']='manual' if row['method'] else 'unresolved'
            if not row['method'] or normalized(row['method']) not in METHODS:
                issues.append({'code':'payment_method_review','field':'method'})
            if not row['location']:issues.append({'code':'location_missing','field':'location'})
            for field in ('source_reviewed','manual_reviewed'):
                cell=mapped.get(field);row[field]=cell['value'] if cell and not cell['issue'] else None
                if row[field] not in (None,'') and not isinstance(row[field],bool) and normalized(str(row[field])) not in ('si','no','yes'):
                    issues.append({'code':'review_flag_unrecognized','field':field})
            for column,original in cells.items():
                cell=dict(original);field=next((k for k,c in mapping.items() if c==column),None)
                value=cell['value']
                if cell['issue'] in ('formula_error','cell_error'):value=cell['reported_value']
                elif cell['issue']=='formula_cache_missing':value=None
                elif field in ('date','amount') and row[field] is not None:value=row[field]
                cell.update(column_label=headers.get(column,{}).get('value') or re.sub(r'\d+$','',cell['cell']),readable_value=value)
                row['cells'].append(cell)
            result['rows'].append(row)
        result['summary']['ignored_empty_rows']=ignored
        numbers=Counter(r['number'] for r in result['rows'] if r['number'])
        groups=defaultdict(list)
        for row in result['rows']:
            if row['number'] and numbers[row['number']]>1:row['issues'].append({'code':'duplicate_payment_number','field':'number'})
            if row['invoice_code']:groups[row['invoice_code']].append(row)
        for row in result['rows']:
            group=groups.get(row['invoice_code'],[])
            row['invoice_payment_rows']=len(group)
            # Evidence across the entire workbook, never an invoice total or paid status.
            row['invoice_payment_total']=f"{sum((Decimal(r['amount']) for r in group if r['date'] and r['amount'] is not None and r['kind']=='ingreso'),Decimal(0)):.2f}"
        if not result['rows']:raise ValueError('no_payments')
    except (zipfile.BadZipFile,KeyError,ET.ParseError,ValueError,RuntimeError,NotImplementedError,OverflowError) as error:
        known={'file_too_large','workbook_limit','unsupported_macros','unsupported_xml','invalid_shared_string','invalid_boolean',
            'missing_payment_sheet','ambiguous_payment_sheets','invalid_workbook_path','invalid_cell_reference','duplicate_header',
            'missing_payment_header','no_payments'}
        result['file_issues']=[str(error) if str(error) in known else 'invalid_workbook']
        # Fail closed: do not present a truncated payment set as a usable preview.
        result['rows']=[]
    dates=[r['date'] for r in result['rows'] if r['date']]
    result['summary'].update(payment_totals(result['rows']),currency='DOP',financial_records_created=0,
        first_date=min(dates,default=None),last_date=max(dates,default=None))
    return result


def read_payment_csv(content):
    """Strict CSV preset using observed payment columns; unknown layouts fail closed."""
    import csv
    result={'parser_version':'alegra-payment-csv-v1','rows':[],'file_issues':[],'summary':{}}
    try:
        if len(content)>MAX_BYTES:raise ValueError('file_too_large')
        if b'\x00' in content:raise ValueError('invalid_payment_csv')
        try:decoded=content.decode('utf-8-sig');encoding='utf-8-sig'
        except UnicodeDecodeError:decoded=content.decode('cp1252');encoding='cp1252'
        candidates=[]
        for delimiter in (';',',','\t'):
            reader=csv.reader(io.StringIO(decoded,newline=''),delimiter=delimiter,strict=True)
            first=next(reader,[])
            names=[normalized(v) for v in first]
            if all(normalized(FIELDS[k]) in names for k in REQUIRED):candidates.append((delimiter,first))
        if len(candidates)!=1:raise ValueError('missing_payment_header')
        delimiter,first=candidates[0]
        if len(first)>256:raise ValueError('workbook_limit')
        mapping={}
        for k,label in FIELDS.items():
            matches=[i+1 for i,v in enumerate(first) if normalized(v) in ({'moneda','currency'} if k=='currency' else {normalized(label)})]
            if len(matches)>1:raise ValueError('duplicate_header')
            if matches:mapping[k]=matches[0]
        def cell(column,line,value):
            letters='';n=column
            while n:n,r=divmod(n-1,26);letters=chr(65+r)+letters
            return {'cell':f'{letters}{line}','type':'inlineStr','value':value,'reported_value':value,
                'formula':None,'formula_attributes':{},'issue':None}
        headers={i+1:cell(i+1,1,v) for i,v in enumerate(first)};rows=[]
        reader=csv.reader(io.StringIO(decoded,newline=''),delimiter=delimiter,strict=True);next(reader)
        for i,values in enumerate(reader,2):
            if i>MAX_SCAN_ROWS or i*len(first)>MAX_CELLS:raise ValueError('workbook_limit')
            if not any(v.strip() for v in values):continue
            if len(values)!=len(first):raise ValueError('invalid_payment_csv')
            rows.append((i,{j+1:cell(j+1,i,v) for j,v in enumerate(values)}))
        result=read_payment_preview(b'',prepared=('Payments CSV',False,headers,mapping,rows))
        result.update(parser_version='alegra-payment-csv-v1',encoding=encoding)
    except (UnicodeError,ValueError,csv.Error) as error:
        result['file_issues']=[str(error) if str(error) in {'file_too_large','missing_payment_header','duplicate_header','workbook_limit'} else 'invalid_payment_csv']
        result['summary']=payment_totals([])
    return result


def read_payment_xlsx(content):
    """Routine XLSX export: identify one payment table without a sheet-name requirement."""
    result=read_payment_preview(content,report_sheet=True)
    result['parser_version']='alegra-payment-xlsx-v2'
    return result
