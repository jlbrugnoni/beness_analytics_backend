"""Comparison-only normalization. Original report and ledger values stay intact."""
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import MD5


def bank_lookup_key(field, key):
    # Bound the index entry even when a report supplies a very long reference.
    return MD5(KeyTextTransform(key, field))


def description_text(value):
    return ' '.join(str(value or '').split())


def comparable_source(source):
    return {**source,'description':description_text(source.get('description'))}


def transaction_facts(source):
    return tuple(source.get(key) for key in ('bank_date','amount','currency','direction')) + (description_text(source.get('description')),)


def identity_fields(source, provider):
    """Popular serials describe terminals/parties; generic references are not IDs."""
    if provider != 'popular':
        return ('reference', 'serial')
    reference = str(source.get('reference') or '').strip()
    return ('reference',) if reference and reference.lstrip('0') not in ('', '1') else ()
