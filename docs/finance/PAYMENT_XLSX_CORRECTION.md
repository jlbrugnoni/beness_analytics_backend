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
