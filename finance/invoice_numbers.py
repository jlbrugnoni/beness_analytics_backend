"""Supported Dominican invoice identities; retain the complete series and sequence."""

# Legacy B01/B02 sequences have eight digits. Observed E31/E32 sequences
# have ten. Do not strip prefixes/zeroes or accept other document types.
INVOICE_CODE_PATTERN = r'(?:B0[12][0-9]{8}|E3[12][0-9]{10})'
