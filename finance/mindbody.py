"""Source-linked Mindbody collections; no copied sales or GET-time database writes."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from django.db.models import F

from core_data.models import SaleRawRow, ReportImport, Studio
from .mapping import source_rules, resolve_source_values
from .models import MindbodySaleAssignment, normalized_source_value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return None
        return number.quantize(Decimal('.01'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def source_groups(company, code=None):
    """Latest completed source snapshot per sale, not additive SaleLine revisions.

    An overlapping date-range report contains the complete item/payment group for
    each included sale. Missing sales in a report do not imply cancellations.
    Invalid rows with a known sale number remain visible and block review.
    """
    qs = SaleRawRow.objects.filter(site_id=company.site_id,
        report_import__report_type='sales', report_import__source_system='mindbody',
        report_import__status=ReportImport.STATUS_COMPLETED)
    if code is not None:
        # JSON keys contain spaces and punctuation: construct the lookup literally.
        qs = qs.filter(**{'normalized_payload__No. de Venta': code})
    qs = qs.order_by(F('report_import__processed_at').desc(nulls_last=True), '-report_import_id', 'row_number').values(
        'report_import_id', 'row_number', 'normalized_payload', 'is_valid', 'validation_errors',
        'report_import__file_name', 'report_import__processed_at', 'report_import__uploaded_by_id')
    grouped = {}
    for row in qs.iterator(chunk_size=1000):
        number = str(row['normalized_payload'].get('No. de Venta') or '').strip()
        if not number:
            continue
        group = grouped.setdefault(number, {'report': row['report_import_id'], 'rows': [],
            'file_name': row['report_import__file_name'], 'processed_at': row['report_import__processed_at'], 'older': {}})
        if row['report_import_id'] == group['report']:
            group['rows'].append(row)
        else:
            group['older'].setdefault(row['report_import_id'], {'rows': []})['rows'].append(row)
    return grouped


def build_source(code, group):
    rows = group['rows']
    issues = set()
    dates = {r['normalized_payload'].get('_sale_date') for r in rows}
    clients = {str(r['normalized_payload'].get('ID del Cliente') or '') for r in rows}
    customers = {str(r['normalized_payload'].get('Cliente') or '') for r in rows}
    labels = {str(r['normalized_payload'].get('Localidad') or '') for r in rows}
    if any(not r['is_valid'] for r in rows): issues.add('invalid_source_rows')
    if len(dates) != 1 or None in dates: issues.add('source_date_conflict')
    if len(clients) != 1 or '' in clients: issues.add('source_customer_conflict')
    if len(labels) != 1: issues.add('source_studio_conflict')
    payments = defaultdict(lambda: {'amount': Decimal(0), 'label': ''})
    items = []
    # Identical item facts on distinct method rows can describe one split payment.
    # Consolidate only when the slices add exactly to that item's reported total.
    item_groups = defaultdict(list)
    for row in rows:
        p = row['normalized_payload']
        label = str(p.get('Forma de Pago') or '')
        key = normalized_source_value(label)
        paid = money(p.get('_paid_total'))
        total = money(p.get('_item_total'))
        if paid is None or total is None:
            issues.add('invalid_source_amount'); paid = paid or Decimal(0); total = total or Decimal(0)
        payments[key]['amount'] += paid
        payments[key]['label'] = label
        item = {'name': p.get('Nombre del artículo') or '', 'quantity': str(p.get('_quantity') or 0),
                'total': f'{total:.2f}', 'tax': str(p.get('_tax') or 0),
                'computation_number': p.get('Computación #') or ''}
        identity = digest({k: p.get(k) for k in ('ID del Cliente','_sale_date','Nombre del artículo',
            'Computación #','_quantity','_item_price','_subtotal','_discount_amount','_tax','_item_total')})
        item_groups[identity].append((item, key, paid))
    for group_items in item_groups.values():
        if len(group_items) > 1 and len({x[1] for x in group_items}) == len(group_items) and sum(x[2] for x in group_items) == money(group_items[0][0]['total']):
            items.append(group_items[0][0])
        else:
            items.extend(x[0] for x in group_items)
    total = sum((money(item['total']) for item in items), Decimal(0))
    paid = sum((p['amount'] for p in payments.values()), Decimal(0))
    if total != paid: issues.add('item_payment_mismatch')
    if any(p['amount'] < 0 for p in payments.values()) or total < 0: issues.add('refund_requires_review')
    source = {'date': next(iter(dates)) if len(dates) == 1 else None,
              'customer': ' / '.join(sorted(customers)), 'customer_id': ' / '.join(sorted(clients)),
              'invoice_total': f'{total:.2f}', 'paid_total': f'{paid:.2f}', 'currency': 'EUR',
              'studio_label': next(iter(labels)) if len(labels) == 1 else '',
              'original_methods': ' / '.join(sorted(p['label'] for p in payments.values())),
              'status': 'Mindbody sale', 'status_kind': 'paid', 'sale_number': code}
    payment_list = [{'key': key, 'original_method': p['label'], 'amount': f"{p['amount']:.2f}"}
                    for key,p in sorted(payments.items())]
    # Provenance changes on unchanged uploads do not invalidate review tokens.
    source_hash = digest({'source': source, 'items': sorted(items,key=digest), 'payments':payment_list,
                          'issues':sorted(issues)})
    return source, items, payment_list, sorted(issues), source_hash


def serialize(company, code, group, assignment=None, rules=None, studio_names=None):
    source, items, payments, issues, source_hash = build_source(code, group)
    if rules is None: rules = source_rules(company)
    if studio_names is None: studio_names = dict(Studio.objects.filter(site_id=company.site_id).values_list('pk','name'))
    overrides = assignment.assignments if assignment else {}
    resolved = resolve_source_values(company, 'mindbody', {'studio_label':source['studio_label']}, rules=rules)
    studio = overrides.get('studio', resolved['studio'])
    if studio not in studio_names: studio = None
    missing = list(issues)
    if not studio: missing.append('studio')
    for payment in payments:
        interpreted = resolve_source_values(company, 'mindbody',
            {'studio_label':source['studio_label'], 'payment_method':payment['original_method']}, rules=rules)
        override = overrides.get('payments',{}).get(payment['key'],{})
        payment['channel'] = override.get('channel',interpreted['channel']) or ''
        payment['studio'] = override.get('studio') or studio
        payment['studio_name'] = studio_names.get(payment['studio'])
        if not payment['channel']: missing.append('payment_method')
        if not payment['studio_name']: missing.append('payment_studio')
        if interpreted['evidence']['payment_method']['requires_review'] and 'channel' not in override:
            missing.append('payment_mapping_review')
    if resolved['evidence']['studio_label']['requires_review'] and 'studio' not in overrides:
        missing.append('studio_mapping_review')
    missing = sorted(set(missing))
    previous = assignment.source_snapshot if assignment else None
    changed = bool(assignment and assignment.source_hash != source_hash)
    if not assignment:
        for older in group.get('older', {}).values():
            older_source, _, _, _, older_hash = build_source(code, older)
            if older_hash != source_hash:
                changed = True
                previous = older_source
                break
    reviewed = (assignment.reviewed if assignment else True) and not missing and not changed
    locked = assignment.reviewed if assignment else (reviewed or changed)
    revision = assignment.revision if assignment else 0
    token = digest({'source_hash':source_hash,'assignments':overrides,'revision':revision,
                    'studio':studio,'payments':payments,'missing':missing})
    result = {'id':code, 'code':code, 'provider':'mindbody', 'company':company.pk,
        'source':source,'items':items,'payments':payments, 'studio':studio, 'studio_name':studio_names.get(studio),
        'payment_count':len(payments),'payment_methods':sorted({p['channel'] for p in payments if p['channel']}),
        'reviewed':bool(reviewed),'locked':bool(locked),'needs_review':not reviewed,'missing_fields':missing,
        'source_changed':changed,'previous_source':previous if changed else None,
        'assignments':overrides,'revision':revision,'token':token,'source_hash':source_hash,
        'file_name':group['file_name'],'report_import':group['report'],
        'source_rows':[r['row_number'] for r in group['rows']],
        'reconciled':False,'batch':None}
    return result


def sales(company, code=None):
    groups = source_groups(company, code)
    assignments = {a.code:a for a in MindbodySaleAssignment.objects.filter(company=company,code__in=groups)}
    rules = source_rules(company)
    names = dict(Studio.objects.filter(site_id=company.site_id).values_list('pk','name'))
    return [serialize(company,number,group,assignments.get(number),rules,names) for number,group in groups.items()]
