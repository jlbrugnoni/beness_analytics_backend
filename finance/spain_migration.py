"""Spain workbook interpretation, preserving original cells and bank origin."""
import re
from .migration_reader import read_migration_xlsx, totals
from .bank_readers import normalized

VERSION='es-enriched-xlsx-v1'
# Owner-approved corrections, guarded by all observed source facts rather than row
# position. The original workbook bytes/cell values are never rewritten.
DATE_CORRECTIONS={
    ('2026-09-05','2026-05-08','274.50','ON 369092994 0805'):'2026-05-09',
    ('2026-10-05','2026-05-09','192.00','ON 369092994 0905'):'2026-05-10',
    ('2026-12-05','2026-05-11','198.00','ON 369092994 1105'):'2026-05-12',
}


def read_spanish_migration(content,month,studio):
    result=read_migration_xlsx(content,month)
    result['parser_version']=VERSION
    corrected=[];cash_deposits=0;origin_review=0
    for row in result['rows']:
        parsed=row['parsed'];parsed['currency']='EUR';parsed['payment_origin']='bank'
        if not parsed.get('location'):
            parsed['location']=studio.name
            parsed['default_studio_id']=studio.pk
        row['issues']=[i for i in row['issues'] if i['code'] not in ('payment_origin_unknown','location_missing')]
        if row['kind']=='credit':
            description=parsed.get('original_description') or ''
            key=(row['bank_date'],row['operation_date'],row['amount'],description)
            if key in DATE_CORRECTIONS:
                parsed['source_bank_date']=row['bank_date']
                row['bank_date']=parsed['bank_date']=DATE_CORRECTIONS[key]
                row['issues'].append({'code':'approved_date_correction','field':'bank_date'})
                corrected.append({'sheet':row['sheet'],'row':row['source_row'],
                    'original':key[0],'corrected':row['bank_date']})
            terminal=re.fullmatch(r'ON\s+(\d+)\s+\d{4}',description.strip())
            if terminal:parsed['terminal']=terminal[1]
            if normalized(parsed.get('payment_method') or '') in ('efectivo','cash'):
                if normalized(description)=='ingreso cajero':
                    parsed['movement_kind']='internal_transfer'
                    parsed['channel_override']='cash'
                    cash_deposits+=1
                else:
                    # The two transfers labelled Cash are not proven cash receipts
                    # or internal transfers. Keep bank evidence and require a method.
                    parsed['channel_override']=''
                    row['issues'].append({'code':'cash_origin_review','field':'payment_method'})
                    origin_review+=1
        # Blank periods and categories are preserved for later review. The owner
        # explicitly chose Estepona for blank studios, not invented expense dates.
    summary=result['summary']
    summary.update(currency='EUR',unresolved_payment_origins=0,default_studio=studio.pk,
        default_studio_name=studio.name,approved_date_corrections=corrected,
        historical_cash_deposits=cash_deposits,cash_origin_review=origin_review,
        bank_origin_only=True,ignored_sales_sheets=True,
        first_bank_date=min((r['bank_date'] for r in result['rows'] if r['bank_date']),default=None),
        last_bank_date=max((r['bank_date'] for r in result['rows'] if r['bank_date']),default=None),
        all_rows=totals(result['rows']))
    from collections import defaultdict
    for field in ('bank_date','operation_date','expense_period'):
        groups=defaultdict(list)
        for row in result['rows']:
            if row[field]:groups[row[field][:7]].append(row)
        summary[field+'_months']={period:totals(groups[period]) for period in sorted(groups)}
    summary['selected_bank_month']=summary.get('bank_date_months',{}).get(month,totals([]))
    return result
