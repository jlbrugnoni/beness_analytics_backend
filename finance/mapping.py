"""Source interpretation only. Callers enforce permissions and retain raw source/manual history."""
from django.core.exceptions import ValidationError
from .models import ConfigurationChange, SourceMapping, normalized_source_value


def resolve_source_values(company, source, values, manual=None):
    if source not in {'alegra', 'mindbody', 'historical'}:
        raise ValidationError('Unsupported source.')
    manual = manual or {}
    if 'studio' in manual and manual['studio'] and manual['studio'].site_id != company.site_id:
        raise ValidationError('Manual studio must belong to the company site.')
    if 'channel' in manual and manual['channel'] is not None and manual['channel'] not in dict(SourceMapping.CHANNELS):
        raise ValidationError('Unknown manual channel.')
    fields = {'cost_center': 'alegra_cost_center', 'price_list': 'alegra_price_list', 'payment_method': 'alegra_payment_method'} if source == 'alegra' else {
        'studio_label': f'{source}_studio', 'payment_method': f'{source}_payment_method'}
    rules = {(rule.source_field, rule.normalized_value): rule for rule in company.source_mappings.filter(active=True)}
    evidence = {}
    for key, field in fields.items():
        raw = values.get(key, '')
        normalized = normalized_source_value(raw)
        rule = rules.get((field, normalized))
        status = ('mapped' if rule.behavior == 'map' else rule.behavior) if rule else ('unmapped' if normalized else 'missing')
        if field == 'alegra_price_list' and normalized == 'general':
            status = 'neutral'
        evidence[key] = {'source_value': raw, 'status': status,
            'rule_id': rule.pk if rule else None, 'rule_revision': rule.revision if rule else None,
            'studio': rule.studio_id if rule and status == 'mapped' else None,
            'channel': rule.channel if rule and status == 'mapped' else None,
            'requires_review': bool(rule and (rule.requires_review or rule.behavior == 'review'))}
    studio_key = 'cost_center' if source == 'alegra' else 'studio_label'
    primary = evidence[studio_key]
    method = evidence['payment_method']
    studio_id = primary['studio']
    channel = method['channel'] or None
    warnings = []
    studio_review = primary['status'] != 'mapped' or primary['requires_review']
    channel_review = method['status'] != 'mapped' or method['requires_review']
    if primary['status'] != 'mapped': warnings.append('studio_source_unresolved')
    if primary['requires_review']: warnings.append('studio_mapping_requires_review')
    if method['status'] != 'mapped': warnings.append('payment_source_unresolved')
    if method['requires_review']: warnings.append('channel_mapping_requires_review')
    if source == 'alegra':
        price = evidence['price_list']
        if price['status'] in {'unmapped', 'review'} or price['requires_review']:
            warnings.append('price_list_requires_review'); studio_review = True
        if primary['studio'] and price['studio'] and primary['studio'] != price['studio']:
            warnings.append('studio_conflict'); studio_review = True
    studio_origin = 'rule' if studio_id else 'unassigned'
    channel_origin = 'rule' if channel else 'unassigned'
    if 'studio' in manual:
        studio_id = manual['studio'].pk if manual['studio'] else None
        studio_origin = 'manual'
        studio_review = studio_id is None
    if 'channel' in manual:
        channel = manual['channel']
        channel_origin = 'manual'
        channel_review = channel is None
    reasons = []
    if studio_review: reasons.append('studio_requires_review')
    if channel_review: reasons.append('channel_requires_review')
    return {'studio': studio_id, 'channel': channel, 'studio_origin': studio_origin, 'channel_origin': channel_origin,
            'requires_review': bool(reasons), 'review_reasons': reasons, 'warnings': warnings, 'evidence': evidence}


DO_DEFAULTS = [
    ('alegra_payment_method', 'Tarjeta débito', 'payment_link', False),
    ('alegra_payment_method', 'Tarjeta crédito', 'card_terminal', True),
    ('alegra_payment_method', 'Efectivo', 'cash', False),
    ('alegra_payment_method', 'Transferencia', 'transfer', False),
]
DO_STUDIO_LABELS = ('Bella Vista', 'Piantini', 'Arroyo Hondo')


def create_dominican_mappings(company, studios, actor):
    """Caller holds company lock and transaction; existing aliases remain authoritative."""
    from .serializers import SourceMappingSerializer
    rows = [dict(source_field=field, source_value=value, channel=channel, requires_review=review)
            for field, value, channel, review in DO_DEFAULTS]
    rows.append(dict(source_field='alegra_price_list', source_value='General', behavior='neutral'))
    for label in DO_STUDIO_LABELS:
        for field in ('alegra_cost_center', 'alegra_price_list'):
            rows.append(dict(source_field=field, source_value=label, studio=studios[label]))
    created = 0
    for values in rows:
        if company.source_mappings.filter(source_field=values['source_field'], normalized_value=normalized_source_value(values['source_value'])).exists():
            continue
        obj = SourceMapping(company=company, **values)
        obj.full_clean()
        obj.save()
        ConfigurationChange.objects.create(actor=actor, target_type='sourcemapping', target_id=obj.pk,
            target_label=obj.source_value, before={}, after=dict(SourceMappingSerializer(obj).data))
        created += 1
    return created
