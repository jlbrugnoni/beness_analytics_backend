"""Comparison-only normalization. Original report and ledger values stay intact."""
def description_text(value):
    return ' '.join(str(value or '').split())


def comparable_source(source):
    return {**source,'description':description_text(source.get('description'))}
