"""Explicitly approved historical assignments; never relax source/conflict validation."""
from copy import deepcopy


def supervised(batch):
    return bool(batch.migration_batch_id and batch.migration_batch.supervised)


def approve_sale(mapping):
    result=deepcopy(mapping)
    reasons=set(result['review_reasons'])
    if result.get('channel'):reasons.discard('channel_requires_review')
    if result.get('studio') and 'studio_conflict' not in result.get('warnings',[]):
        reasons.discard('studio_requires_review')
    result.update(review_basis='supervised_migration',review_reasons=sorted(reasons),requires_review=bool(reasons))
    return result
