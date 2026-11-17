"""Closure evidence from authoritative Mindbody paid amounts, never invoice copies."""
from . import mindbody


def expected_rows(company, start, end, studio=None):
    from .closures import CHANNELS, amount, money
    structural = {'invalid_source_rows','invalid_source_amount','source_date_conflict',
                  'source_customer_conflict','refund_requires_review'}
    for sale in mindbody.sales(company):
        source = sale['source']
        source_day = source.get('date')
        day = source_day
        if not day:
            day = (sale.get('previous_source') or {}).get('date')
        if day and not start.isoformat() <= day <= end.isoformat():
            continue
        for payment in sale['payments']:
            sid = payment['studio']
            if studio and sid != studio:
                continue
            channel = payment['channel']
            value = amount(payment['amount'])
            reasons = []
            if not source_day or value is None or structural.intersection(sale['missing_fields']):
                reasons.append('invalid_facts')
            if channel not in CHANNELS:
                reasons.append('payment_method')
            include = not reasons
            if not sid: reasons.append('studio_missing')
            if not sale['reviewed']: reasons.append('invoice_review')
            if 'payment_mapping_review' in sale['missing_fields']: reasons.append('method_review')
            yield {'side':'expected','id':f"mindbody:{sale['code']}:{payment['key']}",
                'provider':'mindbody','date':day,'channel':channel,'amount':money(value),
                'studio':sid,'studio_name':payment['studio_name'],'revision':sale['revision'],
                # Includes source, assignments and effective mappings. Identical
                # overlapping reports do not alter this token or a checked day.
                'source_hash':sale['token'],'number':sale['code'],'invoice':sale['code'],
                'sale_id':sale['code'],'sale_revision':sale['revision'],
                'description':source.get('customer') or '', 'currency':'EUR',
                'issues':reasons,'included':include,'source_issues':sale['missing_fields'],
                'file_name':sale['file_name'],'sale_file_name':sale['file_name'],
                'report_import':sale['report_import'],'original_method':payment['original_method']}
