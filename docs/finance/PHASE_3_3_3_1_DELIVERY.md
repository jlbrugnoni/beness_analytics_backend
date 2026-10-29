# Phase 3.3.3.1 — workbook payment source preview

Date: 2026-10-25. Implemented, validated and accepted by client (D-066).
Both repositories remain feature/finance-phase-2. No push/merge/deployment.

## What I did

- Implemented a derived payment preview from Alegra_adm in an existing immutable
  MigrationImportBatch workbook. No new upload, model, migration or original/raw
  rewrite is needed, including previously saved previews #2 and #3.
- New GET /api/finance/migration-imports/{id}/payments/ with selected payment month
  or all dates, exact full invoice-code and review filters, 15-row pagination,
  full-source and filtered summaries. Queries validate scope/review/code/page.
  All dates retains missing/invalid source dates; no invalid date is inferred.
- Preserve payment number, date, amount, account, original associations, customer
  source fields, original/corrected payment methods, studio label, both separate
  review flags, status, derived NCF and original readable cell/formula evidence.
  Metodo overrides no source field; missing corrected method remains unresolved,
  with original Metodo_pago visible. Recognize legacy Yes/No/Sí and booleans as
  review evidence, never as a confirmed bank/sale match.
- Extract one complete invoice code from the observed Facturas: B01/B02... source
  pattern in Asociaciones. Cached NCF is supplementary conflict evidence, never
  required identity or an automatic override. Multiple/unrecognized references,
  missing/repeated/invalid payment numbers, unsupported kinds, invalid/nonpositive
  amounts, missing dates/method/studio and formula-cache problems remain visible.
- Keep separate payment occurrences and show count/positive valid-date income
  amount grouped by referenced invoice across all workbook payment dates. This
  is a source group, not invoice total, allocation, outstanding amount or link.
  Totals include review rows with valid date/positive amount/Ingreso kind, so
  duplicate identifiers are not silently collapsed or certified as receipts.
- Source bounds: 5 MiB input, 50 MiB expanded ZIP, 2,000 distinct entries, 20 MiB
  XML part, 25,000 scanned rows, 20,000 retained payments, 300,000 cells, 256 columns.
  Reject macros, DTD/entities, repeated required headers, ambiguous payment sheets,
  invalid/external sheet paths and malformed cell/shared-string references.
  Package/limit failure returns an explicit error and no partial payment set.
  Formulas are never executed/recalculated. No Excel/runtime dependency added.
- Reuse migration permissions: money/finance/bank/sensitive and whole-company site
  scope. Restricted studios cannot read source payments. Import capability is
  not needed for viewing an authorized existing source. Private/no-store applies.
- Added EN/ES Alegra payment preview panel within an open migration preview:
  Show Alegra payments, month/review filters, invoice search, source totals,
  payment group evidence, source detail and technical cell disclosure. Late
  responses are ignored after source/filter/access changes. No payment data is
  exposed outside the existing finance scope.
- No financial payment/receipt/allocation records or confirmed invoice links are
  created. Existing invoice/bank posting, grants and user source files are untouched.
  Standalone native CSV, refund/void/multi-invoice receipt interpretation, cross-file
  payment identity, posting/undo and settlement matching remain later subphases.

## Source observation

Read-only parser validation against user-uploaded preview #3 (identical to #2):
1,128 dated payment rows, Sep 1–Oct 22; source total 6,512,829.80 DOP; 1,971 blank/
checkbox/formula-template rows ignored. September: 615 entries, 3,555,130.80 DOP,
four invoice groups with multiple payment entries, one missing-number review row.
Alegra_adm!183 retains explicit reference B0200004842 despite blank NCF/Numero.
These results do not certify bank reconciliation, paid sales or source completeness.
Invoice-vs-payment customer/amount/date mismatches from the earlier comparison
are not evaluated by this source-only preview; they remain review work at linking.

## Validation

- PostgreSQL 16: 281 supported tests passed (200 finance plus 81 existing analytics,
  purchase matching/repair and import guards). Ten new payment reader/API tests.
- SQLite: 281 tests discovered, 277 passed, four existing PG concurrency skips.
- Final focused PostgreSQL ten payment tests passed after adding studio-scope
  coverage and aligning group totals with valid dates. Covers split receipts,
  original references/missing NCF, duplicate identities, unsupported references,
  malformed sources, limits, epochs/shared strings, cache errors, month/invoice/
  review/page filters, immutable originals, no financial writes, permissions,
  whole-company scope and read access without import capability.
- Frontend lint/production build and Django migration checks passed. Existing
  unrelated frontend warnings remain. No new DB migrations. Existing legacy
  core_data.tests removed-Center import is outside the supported targeted suite.
- Synthetic browser QA preview #4, alegra-payments-synthetic-qa.xlsx: September
  three payments /395.00; invoice B0200009001 yields two payments 100+200 /300.00;
  review filter yields missing-number entry /95.00; All dates + review includes
  October formula error /145.00. Source dialog preserves readable date, payment
  number, method, amount, original reference and cell evidence. No real source
  screenshot or financial posting; only a clearly named synthetic raw QA batch.
- Logs /private/tmp/finance-payment-preview/{sqlite-tests,pg-tests,pg-focused-final,
  lint,build}.log. Screenshot /private/tmp/finance-payment-preview/payments-preview.png.
- No external review agent, dependency installation, grant change or deployment.

## What you should test

1. Refresh http://127.0.0.1:3037/finance/migration-imports; open user preview #3,
   Ingresos_Egresos_DO_BI2.xlsx under Migration preview QA. Scroll below the existing
   movement preview to Alegra payment preview; click Show Alegra payments.
2. Pilot payment month September should show 615 entries /3,555,130.80 DOP and
   one review row. These are payment source totals, separate from bank/manual totals.
3. Search B0200005029: 1,200 Cierre and 2,400 Efectivo, group two entries /3,600.
   Original and corrected methods stay separately visible. Clear filter afterwards.
4. Review issues: row 183 retains B0200004842 /10,400 and missing payment number.
   Open Payment source cells to inspect Asociaciones, date, number and source flags.
5. All payment dates should show 1,128 entries /6,512,829.80. Return to September;
   try pagination and source cells. No reupload, correction, linking or commit needed.

## Next subphase

After client acceptance, resolve stable receipt identity/cross-file source versions,
then build reviewed receipt/allocation posting and order-independent invoice links.
Native standalone payment export still requires its own verified layout. Do not
infer global uniqueness from 1,127 distinct numbers in this workbook alone.
