# Phase 3.4.1 enriched workbook source preview delivery

Date: 2026-10-25. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. No push, merge or production migration.

## What I did

- Recorded Q-015 answers (D-060–063, BR-064–065): September 2026 pilot; intended
  master through October 22; unknown cash/bank provenance; no split debit rows.
- Inspected the original saved workbook read-only. Its actual copy is the earlier
  partial sample, not a demonstrated October 22 master. Requested the current
  saved master and September 14–30 bank report paths. No full-month coverage or
  real 1–15/14–30 overlap comparison has been performed.
- Added bounded native DR XLSX reader dr-enriched-xlsx-v1 using standard-library
  ZIP/XML, without adding a dependency or executing/recalculating formulas/macros.
  It reads Debitos/Ingresos, retains the full original file, sheet inventory and
  preset column mapping. Comparison/dashboard/Alegra sheets do not add movements.
  Generic user-defined column mapping, CSV and Spain layouts are later work;
  this delivery recognizes the existing Dominican workbook preset only.
- Limits: 5 MiB input, 50 MiB expanded package, 20 MiB per XML part, 2,000 package
  entries, 20,000 retained movement rows, 25,000 scanned rows per movement sheet,
  300,000 cells and 256 columns. Reject duplicate ZIP entries, invalid references,
  DTD/entity declarations, macro packages, duplicate recognized headers/sheets and
  repeated movement-sheet targets. Original failed-file evidence stays private.
- Added migration 0010: MigrationImportBatch/Row with immutable original bytes,
  filename/hash/actor/time/parser, selected month, summaries and raw cell/formula/
  cached-result evidence. Typed transaction/operation/expense dates and signed
  amounts are separate from parsed manual fields. No financial posting occurs.
- Keep original and manual descriptions, reference/serial, legacy review flag,
  expense period, categories, location, payment method, terminal and balance.
  Source income is not an extra Alegra sale. No account/cash origin is guessed;
  every retained row starts unknown and has a visible review issue.
- Ignore checkbox-only/empty template rows, preserving the original workbook.
  Retain nonempty classification-only rows as incomplete review evidence, with
  no fabricated date/amount. Invalid source rows stay available in All entries.
- Preserve cached text and formula errors separately. Errors/missing formula
  results leave derived fields unresolved. Empty cached strings are valid blank
  results, not automatically missing caches. Dates support Excel serial/1904
  epoch and explicit ISO/day-month-year formats; no year inferred from a month.
  Normalize only sub-cent Excel numeric serialization noise, retain original
  values and reject substantive extra precision/nonfinite/out-of-range amounts.
- Preview totals distinguish transaction month, operation month and expense period.
  Income/expense type filters have matching source totals. Totals require valid
  transaction dates/amounts and never prove profit, balances or coverage. Failed
  partial files have explicit partial-evidence warnings.
- Added /api/finance/migration-imports/ history/upload/detail, companies/, rows/
  with month/type filters, source-row/ protected raw detail and original download.
  All reads require finance/money, bank capability, sensitive detail and site-wide
  company scope. Import additionally gates upload/original retrieval. Studio-only
  users cannot expose company-wide payroll/source data. Private/no-store applies
  to every response; no public media/admin bypass. Company site/currency cannot
  change after migration source history. No PATCH, DELETE or commit endpoint.
- Added EN/ES /finance/migration-imports linked from Finance: month/file selector,
  history, coverage/origin warnings, totals/filters, preserved assignments and raw
  cell/formula detail. Separate date bases retain cross-month transactions.

## Observed reference sample

Saved source: Ingresos_Egresos_DO_BI.xlsx at the client-supplied OneDrive path.
Seven sheets; movement sheets Debitos and Ingresos. Source inspected only, never
copied into Git, test fixtures or QA uploads by the agent.

- 42 retained entries: 16 valid debit rows, 25 valid income rows and one incomplete
  category/subcategory-only debit row at Debitos!2661. No movement is invented
  for that incomplete row. 3,917 otherwise empty/checkbox-only rows ignored.
- Observed financial dates: August 31–September 2, 2026.
- September by transaction date: 20 entries, income 443,151.90 DOP and expenses
  244,757.37 DOP. These are partial source figures, not September results.
- All valid source amounts: income 649,862.80 and expenses 388,214.89 DOP.
- By September operation dates: income 211,070.60 DOP; by September expense period:
  expenses 224,757.37 DOP. Different date bases intentionally produce different totals.
- Income terminal/location formulas have 19 saved error results and one valid
  empty-string cache across 49 formula cells. Raw formula/error evidence remains;
  no studio is guessed from a failed cached lookup.
- Every retained payment origin remains unknown, consistent with client evidence.

## Validation

- PostgreSQL 16: 269 tests passed (188 finance + 81 existing analytics/purchase/
  import regressions), including 16 new migration reader/API tests. Final focused
  reader tests also cover bounded XML reads, rounding range and reference checks.
- SQLite: 269 tests discovered, 265 passed and 4 PostgreSQL concurrency tests
  skipped. Focused migration suite passed separately. Existing legacy
  core_data.tests Center import remains outside the supported targeted suite.
- Django system/migration checks and frontend lint/production build passed;
  unrelated existing frontend warnings remain. No external review agent used.
- Browser synthetic QA verified month selection/history; four valid September
  entries with income 275.00/expenses 150.00; operation-month filter income 200.00;
  expense-period filter expenses 50.00; All entries retains a fifth incomplete
  row; source detail preserves cached terminal, Excel error and formula text.
- Synthetic company Migration preview QA, preview #1. Two blank checkbox rows
  ignored. No real source posted/migrated, no bank/sales records changed and no
  user grants changed. Only isolated QA/test DBs migrated.
- Screenshot: /private/tmp/finance-phase3-4-1-migration-preview.png. Source detail
  proof: /private/tmp/finance-phase3-4-1-migration-source.png.

## What you should test

Open http://127.0.0.1:3037/finance/migration-imports with the same QA login.
Choose Migration preview QA to inspect the synthetic example, or your Dominican
QA company and upload the existing workbook with pilot month 2026-09.

1. Confirm real movement rows are retained and blank checkbox rows ignored.
   Verify manual descriptions/categories/periods/review flags and original cells.
2. Change Month basis between transaction, operation and expense period. A bill
   paid in September for August must keep both dates and be excluded from the
   September expense-period filter. Income may settle after its operation date.
3. Check unknown cash/bank origin and saved formula errors are visible, without
   guessed accounts/studios or a blocked preview. All entries includes invalid
   dates and incomplete classification rows; they do not inflate valid totals.
4. Upload the same workbook again: another linked source preview appears, without
   creating transactions or overwriting classifications. Download retains the
   original bytes; the existing workbook on disk is unchanged.

## Remaining work and source dependency

This is a source preview, not migrated financial history. Account/origin decisions,
studio/category resolution, manual cash/expense records, links to existing bank
postings, conflicts, commit/undo and pilot comparison remain Phases 3.4.2–3.4.3.
A Conciliado checkbox preserves prior recognition only, not a reconstructed match.
No complete September pilot can be certified from the present short saved sample.
The current full master and September 14–30 bank report paths remain pending.
Client-provided October 22 cutoff remains intended coverage, not verified data.
