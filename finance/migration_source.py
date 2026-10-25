"""Readable source-cell presentation; never rewrites uploaded evidence."""
import io
import posixpath
import re
import zipfile
from .bank_readers import normalized
from .migration_reader import NS, REL, MAPPINGS, MAX_BYTES, MAX_EXPANDED_BYTES, safe_xml, column_number, cell_value, parse_date, parse_period, parse_money


def source_headers(content, sheet_name):
    """Read original column labels/epoch for already-saved previews, including v1."""
    if len(content)>MAX_BYTES:raise ValueError('file_too_large')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos=archive.infolist()
        if len(infos)>2000 or sum(item.file_size for item in infos)>MAX_EXPANDED_BYTES:
            raise ValueError('workbook_limit')
        workbook=safe_xml(archive,'xl/workbook.xml')
        properties=workbook.find('s:workbookPr',NS)
        epoch1904=properties is not None and properties.get('date1904') in ('1','true')
        relations=safe_xml(archive,'xl/_rels/workbook.xml.rels')
        paths={item.get('Id'):item.get('Target') for item in relations if item.get('TargetMode')!='External'}
        sheet=next((item for item in workbook.findall('s:sheets/s:sheet',NS) if item.get('name')==sheet_name),None)
        if sheet is None:raise ValueError('missing_movement_sheet')
        target=paths.get(sheet.get(REL),'')
        path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target))
        if not path.startswith('xl/') or '..' in path.split('/'):raise ValueError('invalid_workbook_path')
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(t.text or '' for t in item.findall('.//s:t',NS)) for item in safe_xml(archive,'xl/sharedStrings.xml')]
        data=safe_xml(archive,path)
        header=data.find('s:sheetData/s:row[@r="1"]',NS)
        if header is None:raise ValueError('missing_header')
        labels={column_number(item.get('r',''))[0]:cell_value(item,strings)['value'] for item in header.findall('s:c',NS)}
        return labels,epoch1904


def readable_cells(row, labels, epoch1904):
    fields={normalized(label):field for field,label in MAPPINGS.get(normalized(row.sheet),{}).items()}
    result=[]
    for original in row.raw:
        cell=dict(original)
        column=column_number(cell['cell'])[0]
        header=labels.get(column)
        field=fields.get(normalized(str(header or '')))
        value=cell.get('value')
        # Shared-string indexes have already been decoded into value by the
        # immutable reader; reported_value is storage evidence, not display text.
        if cell.get('issue') in ('formula_error','cell_error'):
            value=cell.get('reported_value')
        elif cell.get('issue')=='formula_cache_missing':value=None
        else:
            try:
                if field in ('bank_date','operation_date'):value=parse_date(cell,epoch1904)
                elif field=='expense_period':value=parse_period(cell,epoch1904)
                elif field in ('amount','balance'):
                    amount=parse_money(cell,optional=True)
                    value=f'{amount:.2f}' if amount is not None else None
            except ValueError:
                # Invalid source content stays visible; never substitute a parsed
                # assignment or invent a valid date/amount to hide the problem.
                pass
        cell.update(column_label=header or re.sub(r'\d+$','',cell['cell']),field=field,readable_value=value)
        result.append(cell)
    return result
