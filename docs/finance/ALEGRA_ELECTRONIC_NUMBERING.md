# Alegra invoice numbering compatibility patch

D-099 · 2026-11-03 · Client authorizes a patch committed directly to main.

## Observed issue and correction

The supplied Alegra invoice CSV and native transaction XLSX switch from B01/B02 to
E31/E32 invoice series on 2026-11-02. The invoice reader previously required B01/B02
plus eight digits. The payment reader and historical payment invoice filter had the
same restriction. That rejected 141 invoices and prevented their 141 corresponding
payments from identifying an invoice, despite valid matching source amounts.

A shared pattern now accepts exactly B01/B02 + eight ASCII digits or E31/E32 + ten
ASCII digits. Both formats can coexist in the same report. Preserve the complete
series, zeroes and sequence as the identity; never convert E numbers into B numbers.
Other series, wrong lengths, suffixes and ambiguous multiple references remain
rejected. Invoice/payment matching, cancellation, scope, review and overlap policies
are unchanged. The old case behavior is preserved (invoice CSV uppercase, payment
reference recognition case-insensitive). No schema/data migration is required.

Parser versions now identify the changed interpretation: `alegra-items-v3`,
`alegra-workbook-payments-v2`, `alegra-payment-csv-v2`, `alegra-payment-xlsx-v3`.
English/Spanish invalid-code messages explain both accepted formats.

## Recovery after deployment

Upload both original reports again and use the newly created previews. Original
files need no edits. Existing previews remain immutable evidence with their prior
parser results. The upload APIs parse the bytes again and create new previews even
when the file hash matches an earlier upload. The normal record overlap/matching
flow reuses unchanged existing invoices/payments and preserves their classifications;
no financial reset or deletion is needed. Either report upload order is supported.

Ordinary missing-method/studio review and any genuine source-change decisions remain
in force. `Egreso` transaction rows remain excluded from customer sales collections.
This patch does not turn every warning into an accepted financial record.

## Validation

- Read-only reparse of the actual supplied reports after the patch: 249 invoices
  accepted, zero numbering review invoices, total DOP 1,545,306.00. All 250 income
  payments identify their invoice, and every grouped invoice/payment amount agrees.
  Electronic series: 135 E32 invoices and six E31 invoices. Legacy: 104 B02 and four
  B01 invoices; one legacy invoice has two payments. No source files or financial
  database records were modified by this check.
- Synthetic regressions cover mixed-series parsing, native XLSX references/cached
  numbers, malformed/unsupported/Unicode codes, multiple/trailing references,
  invoice-first/payment-first posting, identical reuploads without duplicate records,
  full-code matching and the historical migration invoice filter.
- Test fixtures contain no customer data. Supplied reports remain outside Git.

- Complete finance PostgreSQL regression suite: 414 tests passed, including the
  seven new numbering tests. Frontend validation-message ESLint check passed.
  Test data used a fresh disposable PostgreSQL cluster; application/production
  records were not modified. No frontend behavior/layout change requires a rebuild
  for validation beyond the translation syntax/lint check.
