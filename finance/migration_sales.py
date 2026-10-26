"""Read Alegra items in a historical workbook through the normal invoice parser.

Only source headers are repaired for the observed legacy encoding. Uploaded bytes,
original cells and saved formula results remain evidence; formulas are not evaluated.
"""
import csv
import io
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError
from .alegra_reader import FIELDS, read_alegra_csv
from .migration_reader import parse_date, parse_money
from .payment_preview import worksheet


def header(value):
    return str(value or '').replace('”','Ó').replace('…','É').replace('È','É')


def read_workbook_sales(content):
    try:
        # Load the named sheet with the same bounded, non-evaluating XLSX reader.
        name,epoch,headers,_,rows=worksheet(content,sheet_name='alegra',field_labels={},required_fields=set())
        labels=[header(headers.get(c,{}).get('value')) for c in range(1,max(headers)+1)]
        from .bank_readers import normalized
        mapping={key:next((i for i,label in enumerate(labels) if normalized(label)==normalized(expected)),None)
            for key,expected in FIELDS.items()}
        if any(index is None for index in mapping.values()):raise ValueError('missing_header')
        if any(sum(normalized(label)==normalized(expected) for label in labels)!=1 for expected in FIELDS.values()):
            raise ValueError('duplicate_required_header')
        output=io.StringIO(newline='');writer=csv.writer(output,delimiter=';');writer.writerow(labels)
        source={};line=1
        for number,cells in rows:
            # Ignore trailing formatting/checkboxes, not incomplete source invoices.
            if not any(cells.get(i+1,{}).get('value') not in (None,'') or cells.get(i+1,{}).get('issue') for i in mapping.values()):continue
            values=['' if cells.get(i,{}).get('value') is None else str(cells[i]['value']) for i in range(1,len(labels)+1)]
            for i,cell in cells.items():
                if cell.get('type')=='n' and i<=len(values) and cell.get('value') not in (None,''):
                    try:values[i-1]=format(Decimal(str(cell['value'])),'f')
                    except InvalidOperation:pass # Normal invoice validation marks unusable numbers.
            for key,index in mapping.items():
                cell=cells.get(index+1)
                try:
                    if cell and cell.get('issue'):raise ValueError()
                    if key=='date':
                        value=parse_date(cell,epoch)
                        values[index]=value[8:10]+'/'+value[5:7]+'/'+value[:4]
                    elif key in ('invoice_total','item_total'):values[index]=str(parse_money(cell))
                except ValueError:values[index]='' # Normal parser marks this invoice invalid.
            evidence=[]
            for column,cell in cells.items():
                readable=cell.get('value')
                if column-1==mapping['date']:
                    try:readable=parse_date(cell,epoch)
                    except ValueError:pass
                elif column-1 in (mapping['invoice_total'],mapping['item_total'],mapping['unit_price']):
                    try:readable=str(parse_money(cell))
                    except ValueError:pass
                evidence.append({**cell,'column_label':headers.get(column,{}).get('value'),
                    'readable_value':cell.get('reported_value') if cell.get('issue') else readable})
            writer.writerow(values);line+=1;source[line]=(number,evidence)
        parsed=read_alegra_csv(output.getvalue().encode('utf-8'))
        parsed.update(encoding='xlsx',parser_version='alegra-workbook-items-v1')
        for row in parsed['rows']:
            if row['row_number'] in source:
                number,cells=source[row['row_number']]
                row['source_line']=row['source_line_end']=number
                # Keep raw strings for normal item evidence/fingerprints. Original cells
                # are separate and never enter invoice fact comparison.
                row['parsed']['workbook_cells']=cells
                row['parsed']['workbook_sheet']=name
                if any(cell.get('issue') for cell in cells):row['issues'].append('workbook_cell_error')
        by_number={row['row_number']:row for row in parsed['rows']}
        for invoice in parsed['invoices']:
            if any('workbook_cell_error' in by_number[n]['issues'] for n in invoice['row_numbers']):
                invoice['issues'].append('workbook_cell_error')
        # Recompute eligibility after adding formula/cache evidence errors.
        eligible=[invoice for invoice in parsed['invoices'] if not invoice['issues'] and not parsed['file_issues']]
        parsed['summary'].update(valid_invoices=sum(i['source']['status_kind']=='paid' for i in eligible),
            cancelled_invoices=sum(i['source']['status_kind']=='cancelled' for i in eligible),
            review_invoices=len(parsed['invoices'])-len(eligible),
            paid_total=f"{sum((Decimal(i['source']['invoice_total']) for i in eligible if i['source']['status_kind']=='paid'),Decimal(0)):.2f}" if not parsed['file_issues'] else None)
        return parsed
    except (ValueError,KeyError,RuntimeError,OverflowError,NotImplementedError,zipfile.BadZipFile,ParseError) as error:
        parsed=read_alegra_csv(b'')
        parsed.update(encoding='xlsx',parser_version='alegra-workbook-items-v1',file_issues=[str(error) if str(error) in
            ('missing_header','duplicate_required_header','workbook_limit','unsupported_xml','unsupported_macros') else 'invalid_workbook'])
        return parsed
