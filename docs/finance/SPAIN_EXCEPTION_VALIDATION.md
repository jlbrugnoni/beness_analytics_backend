# Spain V2 Step 4 — history and exception validation

2026-11-15. In progress, not accepted or complete. Step 3 was accepted by the
owner's instruction to proceed. All changes remain uncommitted on
feature/finance-spain-v2. No production access or changes.

## Scope clarification

Owner explicitly requires Spain historical expense/cash workbook migration before
release. It cannot be deferred. The provided uploads currently contain Caixa and
Mindbody source exports, but no identified Spain historical finance workbook.
Inspect that actual workbook before choosing parser, column mappings, account
provenance or reviewed/completion rules. Do not assume the Dominican workbook
layout or default-bank-origin rule applies in Spain. Do not reset existing data.

## Step 4.1 evidence completed so far

Found a real split-method example in the already provided April Mindbody Sales
export: sale301 on2026-04-09, one165.00 membership item,5.00Cash and160.00Card.
Source repeats the165.00 item on both method rows. The Step 2 adapter correctly
returns one item/one sale and two payments, totaling165.00 rather than330.00.
October and April contain no negative refund rows in the inspected exports.

Loaded the April source through the existing Analytics import service into the
local Finance QA ES site after backing up SQLite. Original source file remains in
workspace uploads outside Git. No mapping, permission or existing October entries
were overwritten; no April bank/cash receipts were fabricated. Sale301 is available
in QA spain company -> Mindbody sales (clear October dates or select April).

Added four tests through native Analytics imports and operational closure paths:

- Split item layout160Card/5Cash; revised155Card/10Cash replaces the prior source
  group without duplicate collections. Repeat source token remains stable.
- Synthetic negative refund source is preserved pending, not converted to positive
  income or auto-reviewed. This is safety validation, not accepted refund logic.
- Separate36.00 terminal fee debit and36.00 reimbursement credit remain active;
  reimbursement excluded from customer collections; gross card deposits have zero
  withholding, without another fee deduction in daily collections.
- Actual studio cash receipt followed by a bank cash deposit classified internal
  movement counts the receipt once. No paired-transfer/balance-verification feature
  is claimed.

23 targeted exception/cash/Spain-closure tests passed on PostgreSQL. No schema drift.
The existing four exception cases also passed on SQLite. Original importer and
Analytics behavior were reused without modification. Test workbook fixtures contain
synthetic customer details; original financial reports are not committed.

## Remaining Step 4 work

1. Receive/identify Spain's historical workbook; inspect sheets, headers, source
   values/formulas, dates, origin/account fields, categories and review flags.
2. Resolve only business ambiguities revealed by that file, then implement a
   supervised scoped preview/import with explicit account mapping, source retention,
   audit/recovery, overlap preservation, migration permission and completion rules.
3. Test month-by-month against workbook and routine overlaps, preserving existing
   manual bank/cash entries and preventing expected Mindbody cash from becoming
   fabricated actual receipts.
4. Verify a real refund layout or explicitly document an owner-approved pending
   handling limitation. Do not infer links to original sales, original management
   period or refund payment date from negative values alone. Analytical result
   calculations remain a later module.
5. Present final Step 4 owner tests; wait for acceptance and explicit commit/
   progression. Step 5 release readiness has not begun.

User-facing file destination: /Users/joseluisbrugnoni/Beness_analytics/uploads.
This directory is outside both Git repositories; use it for sensitive original
files, never version them into application source.


## Historical workbook discovery — 2026-11-15

Received uploads/Ingresos_Egresos_ES.xlsx; inspected read-only, no source changes,
no saved migration preview and no financial posting. Reused the native XML reader
only for structure/count analysis; its current DOP labels are not an ES importer.

Movement sheets retain the DR template's main headers, but the debit review column
D has a Boolean header rather than Conciliado. Debitos has359 monetary/date rows
from July2025 through November2026; Ingresos has229. All588 have readable dates and
amounts;4668 empty/prefilled rows are not movements. Expense amounts total233760.79;
income amounts total233761.52. Totals are source evidence, not operating results.

Every movement lacks a usable studio.152 expense categories and188 expense months
are blank; three classified expenses lack a subcategory. Income formula errors are
128 terminal and128 studio lookups, not invalid monetary amounts. Preserve original
formula evidence, resolve the confirmed terminal through actual Spain configuration,
and never seed Spain settings from the workbook's Datos template rows (which also
contain Dominican terminal references). Balance General/Cierres are derived views.
Alegra tabs include template/foreign source content and are not authoritative Spain
sales. Existing Analytics Mindbody remains authoritative; do not bulk import these
other sales sheets into Finance or overwrite the weekly Analytics reports.

Critical origin finding:16 incomes labelled Efectivo total25313.65 and all have bank
source descriptions/balances:14 INGRESO CAJERO deposits, one transfer and one TRASPASO.
Do NOT reuse the Dominican cash_label=>cash_account historical posting rule for
these rows: they are not proven actual studio cash receipts. Owner clarification
requested on whether cash was historically recorded only when banked or separately.
Keep transfer principals distinct from customer receipts and preserve balances/source.

All94 supplied September–October Caixa transactions match workbook movements on
date+amount+bank concept. Two extra workbook entries fall in that window because
of suspected month/day errors: Ingresos row86,274.50, bank2026-09-05 versus operation
May8/ON0805; row87,192.00, bank2026-10-05 versus operationMay9/ON0905. Row88,198.00,
has bank2026-12-05 versus operationMay11/ON1105. Proposed bank dates May9/May10/May12
need owner confirmation or a May bank report; do not silently correct them. These
are stored Excel dates, not fixed merely by changing display format. Their exact
source cells are A86/A87/A88; F86/F87/F88 carry operation dates.

Owner questions pending: cash origin/treatment, default Estepona versus company-wide
Administration, missing expense-month treatment, and date anomalies. Bank overlap
implementation must enrich missing expense bank metadata without duplicate imports,
retain manual assignments and use explicit conflict decisions when identity is not
unique. Workbook importer implementation remains pending these source semantics.
