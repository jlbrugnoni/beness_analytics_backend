"""Comparison-only handling of the observed Mac Roman legacy export mistake."""
from .bank_readers import normalized


def decoded_legacy(value):
    try:
        return value.encode('mac_roman').decode('cp1252')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def comparison_copy(value, expected):
    """Change a string only if its reversible decoding exists in the other source.

    Callers still compare all invoice facts/items; this is not fuzzy name matching
    and must only be used with confirmed historical-workbook provenance.
    """
    targets=set(strings(expected))
    def visit(item):
        if isinstance(item,str):
            decoded=decoded_legacy(item)
            return decoded if decoded in targets else item
        if isinstance(item,dict):return {key:visit(value) for key,value in item.items()}
        if isinstance(item,list):return [visit(value) for value in item]
        return item
    return visit(value)


def customer_equal(left,right):
    # The caller also checks exact invoice code, company, status and allocation.
    return (normalized(left)==normalized(right) or
            normalized(decoded_legacy(left))==normalized(right) or
            normalized(left)==normalized(decoded_legacy(right)))
