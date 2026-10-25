"""Sales ledger operations; callers hold the company lock and enforce privacy."""
import hashlib
from copy import deepcopy
import json
from collections import Counter
from rest_framework import serializers
from .bank_readers import normalized
from .configuration import ConfigurationConflict
from .mapping import resolve_source_values
from .models import FinancialSale, SalesPosting, SalesDecision, SalesEvent

VERSION = 'alegra-posting-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def token(company, batch, purpose='plan'):
    # Mapping edits also take the company lock. Snapshot their revisions, because
    # Company.revision describes company configuration, not every source rule.
    rules = list(company.source_mappings.order_by('pk').values_list('pk', 'revision'))
    return digest([VERSION, company.pk, company.sales_revision, company.revision, rules, batch.pk, purpose])


def advance(company):
    company.sales_revision += 1
    company.save(update_fields=['sales_revision'])


def state(sale):
    return {'id': sale.pk, 'code': sale.code, 'source': sale.source, 'items': sale.items,
        'studio': sale.studio_id, 'channel': sale.channel, 'assignments': sale.assignments,
        'cancellation_treatment': sale.cancellation_treatment, 'replacement': sale.replacement_id,
        'cancellation_note': sale.cancellation_note, 'revision': sale.revision, 'active': sale.active,
        'reconciled': sale.reconciled}


def event(posting, actor, action, sale=None, before=None, note='', after=None):
    SalesEvent.objects.create(posting=posting, actor=actor, action=action, sale=sale,
        before=before or {}, after=state(sale) if sale else (after or {}), note=note)


def snapshots(batch):
    """Interpret stored cells without modifying v1 previews or their summaries."""
    item_rows = {}; customers = {}; header = []
    for row in batch.rows.all():
        if row.kind == 'header':
            header = row.raw
        if row.kind != 'data':
            continue
        customers[row.row_number] = row.parsed.get('customer', '')
        occurrences = Counter(); evidence = []
        for name, value in zip(header, row.raw):
            key = normalized(name); occurrences[key] += 1
            if key.startswith('producto/servicio - ') or key == 'subtotal - productos/servicios':
                evidence.append([key, occurrences[key], value.strip()])
        item_rows[row.row_number] = {'name': row.parsed.get('item_name'), 'quantity': row.parsed.get('quantity'),
            'unit_price': row.parsed.get('unit_price'), 'total': row.parsed.get('item_total'),
            'evidence': sorted(evidence, key=lambda entry: (entry[0], entry[1]))}
    result = []
    for invoice in batch.invoices.all():
        source = dict(invoice.source)
        source.setdefault('customer', customers.get(invoice.row_numbers[0], '') if invoice.row_numbers else '')
        source['status_kind'] = {'cobrada': 'paid', 'anulada': 'cancelled'}.get(normalized(source.get('status', '')), 'review')
        issues = [issue for issue in invoice.issues if issue != 'status_requires_review']
        if source['status_kind'] == 'review':
            issues.append('status_requires_review')
        items = [item_rows[number] for number in invoice.row_numbers if number in item_rows]
        if len(items) != invoice.item_count:
            issues.append('missing_source_items')
        result.append({'invoice': invoice, 'source': source, 'items': items, 'issues': issues})
    return result


def facts(source, items):
    header = {key: value for key, value in source.items() if key not in ('status', 'status_kind', 'item_sum')}
    return digest([header, sorted(items, key=lambda item: json.dumps(item, sort_keys=True))])


def outcome(snapshot, sale):
    if snapshot['issues']:
        return 'invalid'
    if not sale:
        return 'new'
    if facts(snapshot['source'], snapshot['items']) != facts(sale.source, sale.items):
        return 'anomaly'
    if snapshot['source']['status_kind'] != sale.source['status_kind']:
        return 'cancellation' if snapshot['source']['status_kind'] == 'cancelled' else 'stale_paid'
    return 'unchanged'


def plan(batch, company):
    posting = SalesPosting.objects.filter(batch=batch).first()
    sales = {sale.code: sale for sale in FinancialSale.objects.filter(company=company, provider=batch.provider, active=True)}
    decisions = {decision.invoice_id: decision for decision in posting.decisions.select_related('sale')} if posting else {}
    rows = []; counts = Counter()
    for snapshot in snapshots(batch):
        invoice = snapshot['invoice']; sale = sales.get(invoice.code)
        decision = decisions.get(invoice.pk)
        status = outcome(snapshot, sale)
        counts[decision.resolution if decision else status] += 1
        rows.append({'invoice_id': invoice.pk, 'code': invoice.code, 'source': snapshot['source'],
            'item_count': invoice.item_count, 'items': snapshot['items'], 'issues': snapshot['issues'], 'outcome': status,
            'decision_id': decision.pk if decision else None, 'decision_revision': decision.revision if decision else None,
            'resolution': decision.resolution if decision else None, 'sale': state(sale) if sale else None})
    return {'token': token(company, batch), 'interpretation_version': VERSION, 'counts': dict(counts), 'rows': rows, 'posting': posting}


def commit(batch, company, actor, expected):
    posting = SalesPosting.objects.filter(batch=batch).first()
    if posting:
        if posting.status == 'active': return posting
        raise ConfigurationConflict('Upload a fresh source preview after undo.')
    if token(company, batch) != expected:
        raise ConfigurationConflict('Sales or mappings changed. Reload the plan.')
    if batch.status != 'preview':
        raise serializers.ValidationError('A failed source file cannot be posted.')
    posting = SalesPosting.objects.create(batch=batch, actor=actor)
    for snapshot in snapshots(batch):
        invoice = snapshot['invoice']
        sale = FinancialSale.objects.filter(company=company, provider=batch.provider, code=invoice.code, active=True).first()
        status = outcome(snapshot, sale)
        resolution = 'pending'
        if status == 'new':
            mapping = resolve_source_values(company, 'alegra', snapshot['source'])
            sale = FinancialSale.objects.create(company=company, provider=batch.provider, code=invoice.code,
                source=snapshot['source'], items=snapshot['items'], created_from=invoice,
                studio_id=mapping['studio'], channel=mapping['channel'] or '', assignments=mapping)
            resolution = 'created'; event(posting, actor, 'create', sale)
        elif status == 'unchanged':
            resolution = 'linked'; event(posting, actor, 'link', sale)
        elif status == 'invalid':
            resolution = 'invalid'
        SalesDecision.objects.create(posting=posting, invoice=invoice, sale=sale, resolution=resolution)
    event(posting, actor, 'commit', after={'interpretation_version': VERSION})
    advance(company)
    return posting


def resolve(decision, company, actor, action, note, expected_revision):
    if decision.posting.status != 'active' or decision.resolution != 'pending' or decision.revision != expected_revision:
        raise ConfigurationConflict('The decision changed or this posting is no longer active.')
    sale = decision.sale
    if not sale or not sale.active:
        raise ConfigurationConflict('The current sale is no longer active.')
    if action == 'cancel':
        snapshot = next(item for item in snapshots(decision.posting.batch) if item['invoice'].pk == decision.invoice_id)
        if outcome(snapshot, sale) != 'cancellation':
            raise serializers.ValidationError('Only an unchanged invoice with confirmed Anulada status can be cancelled here.')
        if sale.reconciled:
            raise serializers.ValidationError('Resolve the reconciliation before cancelling this sale.')
        before = state(sale)
        sale.source = {**sale.source, 'status': snapshot['source']['status'], 'status_kind': 'cancelled'}
        sale.revision += 1; sale.save(update_fields=['source', 'revision'])
        decision.resolution = 'cancelled'; event(decision.posting, actor, 'cancel', sale, before, note)
    elif action == 'retain':
        decision.resolution = 'retained'; event(decision.posting, actor, 'retain', sale, note=note)
    else:
        raise serializers.ValidationError('Choose cancel or retain current facts.')
    decision.revision += 1; decision.save(update_fields=['resolution', 'revision'])
    decision.posting.revision += 1; decision.posting.save(update_fields=['revision'])
    advance(company)


def edit_sale(sale, posting, company, actor, values, note):
    if sale.reconciled:
        raise serializers.ValidationError('Reconciled sales cannot be edited here.')
    before = state(sale)
    # An edit to one assignment must not re-run newer default mappings for the
    # other field. Preserve the mapping snapshot and untouched origins/evidence.
    mapping = deepcopy(sale.assignments)
    reasons = set(mapping.get('review_reasons', []))
    if 'studio' in values:
        sale.studio = values['studio']
        mapping.update(studio=sale.studio_id, studio_origin='manual')
        reasons.discard('studio_requires_review')
        if sale.studio_id is None: reasons.add('studio_requires_review')
    if 'channel' in values:
        sale.channel = values['channel'] or ''
        mapping.update(channel=values['channel'], channel_origin='manual')
        reasons.discard('channel_requires_review')
        if not sale.channel: reasons.add('channel_requires_review')
    mapping.update(requires_review=bool(reasons), review_reasons=sorted(reasons))
    sale.assignments = mapping
    if 'cancellation_treatment' in values:
        if sale.source['status_kind'] != 'cancelled':
            raise serializers.ValidationError('Cancellation treatment requires an Anulada invoice.')
        treatment = values['cancellation_treatment']; replacement = values.get('replacement')
        if treatment == 'replacement':
            if not replacement or replacement.pk == sale.pk or not replacement.active or replacement.company_id != company.pk or replacement.source.get('status_kind') != 'paid':
                raise serializers.ValidationError('Select another active paid invoice in the same company.')
        elif replacement:
            raise serializers.ValidationError('A replacement link requires replacement treatment.')
        sale.cancellation_treatment = treatment
        sale.replacement = replacement if treatment == 'replacement' else None
        sale.cancellation_note = note
    sale.revision += 1; sale.save()
    event(posting, actor, 'edit', sale, before, note)
    advance(company)


def undo_plan(posting, company):
    eligible = []; protected = []; reused = 0
    for decision in posting.decisions.select_related('sale'):
        sale = decision.sale
        if decision.resolution == 'cancelled':
            protected.append({'sale_id': sale.pk, 'reason': 'approved_cancellation'})
        elif decision.resolution != 'created':
            if sale: reused += 1
        elif sale.active:
            reason = None
            if sale.reconciled: reason = 'reconciled'
            elif sale.revision != 1: reason = 'changed'
            elif sale.replaces.filter(active=True).exists(): reason = 'replacement_link'
            elif sale.decisions.filter(posting__status__in=['active','partial_undo']).exclude(posting=posting).exists(): reason = 'other_import'
            if reason: protected.append({'sale_id': sale.pk, 'reason': reason})
            else: eligible.append(sale.pk)
    return {'token': token(company, posting.batch, f'undo:{posting.pk}:{posting.revision}'),
        'eligible': eligible, 'protected': protected, 'reused': reused}


def undo(posting, company, actor, expected, note):
    previous = posting.events.filter(action='undo', after__request_token=expected).first()
    if previous: return previous.after
    result = undo_plan(posting, company)
    if result['token'] != expected or posting.status not in ('active','partial_undo'):
        raise ConfigurationConflict('Undo changed. Reload the preview.')
    for sale in FinancialSale.objects.filter(pk__in=result['eligible']):
        before = state(sale); sale.active = False; sale.revision += 1
        sale.save(update_fields=['active','revision']); event(posting, actor, 'reverse', sale, before, note)
    posting.status = 'partial_undo' if result['protected'] else 'undone'
    posting.revision += 1; posting.save(update_fields=['status','revision'])
    result['request_token'] = expected; result['status'] = posting.status
    event(posting, actor, 'undo', note=note, after=result); advance(company)
    return result
