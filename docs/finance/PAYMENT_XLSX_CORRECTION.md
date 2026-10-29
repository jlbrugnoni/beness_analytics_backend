# Routine Alegra payment XLSX correction

Date: 2026-10-25. Implemented and validated; client retest pending.

Client clarified that Alegra_adm is downloaded as XLSX. The prior routine CSV-only
upload restriction was a developer assumption, not an accepted business requirement.
XLSX is now the primary routine payment input; CSV compatibility remains optional.

## Change

- POST /api/finance/payment-imports/ accepts .xlsx directly (up to 5 MiB), using
  alegra-payment-xlsx-v1. No conversion, enriched workbook, Debitos/Ingresos sheets
  or manual studio/corrected-method fields are required for the routine report.
- Detect a single table using the observed required payment columns, irrespective
  of worksheet name. Search the first 25 source row numbers of at most 100 sheets,
  allowing title/company preamble rows; preserve original row/cell references.
  More than one matching table is an explicit ambiguity error. Unknown column
  layouts remain unsupported/reviewable rather than being guessed.
- Reuse bounded ZIP/XML, shared-string/date epoch/money/formula-cache handling,
  limits, macro/DTD/external-path rejection, source evidence and shared receipt
  posting/identity/overlap protections. Native numeric dates and payment numbers
  are decoded, original bytes/cells preserved. Currency/Moneda are recognized.
- Historical named Alegra_adm preview behavior and previous source snapshots remain
  unchanged; routine report detection is a separate parser mode/version. Direct
  XLSX imports have origin=report and no migration dependency.
- Payment imports file chooser and EN/ES guidance now prioritize original XLSX.
  Existing receipt identity and manual corrections survive XLSX reuploads and
  overlap with historical imports. Saving an upload is still preview only.
- No models/migration, new dependency or user grant changes. No real financial
  posting or source-file change by the agent.

## Validation

- PostgreSQL: 305 supported regression tests passed, including six new XLSX tests.
  SQLite: 305 discovered, 299 passed and six existing PG-only races skipped.
- New cases: standalone differently named worksheet with title rows, no enriched
  columns, native numeric dates/IDs, full existing workbook, ambiguous tables,
  limits/macros/malformed files, routine API upload/original bytes, repeated upload
  and historical overlap preserving a manually corrected recurring method.
- Read-only actual uploaded workbook #3 check: 1,128 payments, Sep 1–Oct 22,
  source total 6,512,829.80 DOP, one missing-number review row; zero file errors.
  This checks the uploaded workbook's observed table, not every vendor layout.
- Frontend lint/build and migration consistency checks passed. Browser confirms
  .xlsx,.csv chooser and XLSX-first guidance on the normal Payment imports page,
  using synthetic company/data only. The chooser was not used to upload a real
  report in browser QA; multipart XLSX upload is exercised by API tests.
- Logs /private/tmp/finance-payment-xlsx-{pg,regression,tests,lint,build}.log.
  Screenshot /private/tmp/finance-payment-xlsx-upload.png.

## Client retest

Refresh http://127.0.0.1:3037/finance/payment-imports, choose the appropriate company,
select the original Alegra payment XLSX and Save payment report preview. Inspect
counts, amounts, references and issues before confirming financial import. No
CSV conversion or worksheet renaming should be needed for the observed columns.
A new native header variation must be checked against the original export if the
preview reports missing/ambiguous columns; never silently reinterpret a table.


## Actual native transaction export: report #4 correction

2026-10-25: The client uploaded the original transaction XLSX as PaymentImportBatch
#4. It was retained with `missing_payment_header`, zero parsed rows and no posting.
The previous validation used the prepared workbook, whose labels differ from this
vendor export. This was a reader defect, not a client file-format error.

Read-only inspection of the retained source found one worksheet (`Worksheet`),
13 columns, a row-1 header and 682 transaction rows. Verified native aliases:
`RNC o Cédula` → customer ID, `Tipo de nota débito` → entry kind,
`Conciliada?` → source review evidence, `Método de pago` → original payment method.
`Número` already normalizes to the existing number field. The routine XLSX reader
now supports these explicit labels as `alegra-payment-xlsx-v2`, while the named
historical workbook preset remains unchanged. Duplicate aliases still fail closed.
No arbitrary column guessing or source identity/amount changes were introduced.

Actual source validation: 615 incoming payments, 3,555,130.80 DOP, September 1–30,
2026, four invoice groups with multiple payments, no missing payment numbers,
zero file errors. The other 67 rows are `Egreso` entries: retained as unsupported
payment evidence, excluded from incoming totals and ineligible for receipt posting.
This payment importer does not import those rows as expenses. Missing manual studio
and corrected-method columns remain review evidence; existing default mappings and
invoice-link rules still apply. These are preview facts, not completed reconciliation.

The screen now shows selected-file success/failure beside the uploader and marks
failed reports in history. A failed routine preview offers **Read saved report
again**. POST `/api/finance/payment-imports/{id}/reread/` requires existing whole-
company finance/sensitive/bank scope and import permission, locks the company,
reuses the retained original bytes, and creates a new preview. The original failed
snapshot remains immutable; the matching-byte duplicate reference preserves its
source relationship. Successful, historical or posted sources cannot use this action.
It never creates receipts, invoices or bank movements automatically.

Validation: all 307 supported PostgreSQL regression tests passed; SQLite passed
301 with six existing PostgreSQL-only skips. Frontend lint/build passed (existing
unrelated hook warnings). Synthetic native-header reader/API tests cover incoming
vs outgoing entries, original field labels, preserved failed evidence, safe re-read,
permission denial and prevention of re-reading a successful preview. Browser QA:
synthetic failed batch #5 → re-read preview #6, two new candidates and one invalid
expense; no financial posting. Screenshot:
`/private/tmp/finance-native-header-retry.png`. Logs:
`/private/tmp/finance-native-header-{tests,pg,lint,build}.log`.

Client test: refresh Payment imports, select report #4 / Review payment import,
then **Read saved report again**. Expect a new preview with 682 source rows,
615 incoming candidates and 67 unsupported expense rows, incoming total
3,555,130.80 DOP. Existing posted payments, if any, may be categorized as existing
or conflicts by the shared identity checks. Review the plan before committing.
No need to upload the original again. Agent left real report #4 unchanged and
unposted; only synthetic previews were created during browser verification.
Changes are local to `feature/finance-phase-2`; no push, merge or deployment.
