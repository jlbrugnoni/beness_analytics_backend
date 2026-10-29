# Historical bank import and simpler migration screen

Delivered locally 2026-10-26 on feature/finance-phase-2 in both repositories.
Client acceptance pending. This is the bank-entry part of historical migration;
cash/manual ledger creation, full migration certification, reconciliation and
monthly results remain unfinished. No production deployment or real workbook posting.

## Problem and resulting workflow

The workbook screen previously saved source previews but had no bank-posting path.
The payment-origin warning was therefore confusing: it described a real uncertainty
but did not provide an action to resolve it. A file could look readable without
creating any operational bank records.

The screen now opens all workbook dates, with All entries / Bank debits / Bank
credits tabs. Optional date-range filters replace the pilot-month/entries/month-basis
controls. These filters affect display and totals only; selection is explicit and
can span all dates. Selecting all eligible rows is labelled accordingly. Source
month metadata remains for compatibility, inferred when omitted; it never truncates
the workbook or bank-import selection. The Alegra payment section is secondary.

Choose a destination bank account, select bank-paid rows, confirm their origin,
then choose Review and import selected bank entries. The existing bank posting
preview shows new/unchanged/ambiguous/conflicting rows. Import transactions and its
confirmation perform the final commit. Missing business classifications can be
completed in Records; they do not require fixing the whole workbook before import.
The prepared import/status can be reopened from the workbook history.

Explicit Efectivo/Cash credits and rows with missing/zero amounts or invalid bank
dates cannot be imported to a bank account. Unlabelled manually entered expenses
are not inferred to be bank-paid: the user must exclude cash rows and confirm the
selected rows. They remain in the immutable workbook preview for later work.

If a preview belongs to a company with no bank account, the UI offers account
configuration or an explicit Copy preview to another authorized Dominican company.
Copying creates a new source preview, preserving the original bytes/rows and original
company preview. It does not post financial records or move any existing records.

## Posting and overlap safeguards

- Derived BankImportBatch/BankImportRow records retain original XLSX bytes, file hash,
  workbook/row lineage and a prepared assignment snapshot. Migrations 0014/0015 add
  this provenance. Normal bank planning, permissions, locks, audit and undo are reused.
- Manual descriptions, expense/operation dates, exact configured categories and
  subcategories, studio/administration, method and compatible terminal are carried
  forward. Unknown labels remain visible as original workbook evidence; configuration
  is not invented. Legacy reviewed is retained only when current required fields are
  complete; it never means reconciled. Imported source facts remain read-only.
- Later raw bank reports can link to historical entries when date/amount/currency/
  direction match, shared source values do not conflict, and there is a shared bank
  reference, serial or balance anchor. Date and amount alone do not silently merge.
  Genuine equal occurrences remain distinct. Linked raw reference/serial evidence is
  retained for later source-change detection without overwriting original evidence.
- Bank-first imports can fill compatible empty classifications. Conflicting workbook
  assignments require review and cannot create a second money record or be applied
  as a bank source correction. Reviewed/edited/reconciled records are protected.
  Reconciled records never receive automatic historical assignment updates.
- The same active workbook source occurrence cannot be posted to another account
  within the company. Changes in that source's posting state invalidate stale plans.
  Company/account/studio scope and import/change permissions remain enforced.
- Undo preserves original workbook evidence and follows existing dependency checks.
  Missing or newly incompatible configuration requires a fresh preparation.

## Current client workbook and setup

Preview 6, Ingresos_Egresos_DO_BI2.xlsx, remains unchanged and unposted in company 5,
Migration preview QA. It has 327 retained bank-sheet rows: 152 debits / 175 credits;
326 have valid bank dates and amounts. There are 311 valid August rows and 15 dated
September 1. Observed dates are August 2–September 1, not proof of full-month coverage.
Debitos!2796 has invalid bank date/amount evidence and remains pending. Four credits
are explicitly Efectivo and remain outside bank posting. Other rows can still need
classification/configuration review; eligibility does not certify bank origin.

Company 5 has no bank accounts. Popular operating/savings accounts and the DR terminal
configuration belong to company 1, QA financial company. The client has not yet
answered whether to use that company consistently, nor whether unlabelled expenses
include cash. Do not silently choose an account/company or assume all rows are bank.
The UI now lets the client make both choices concretely without another upload.

Before schema changes, a full verified SQLite/source-blob backup including preview 6
was saved outside Git in .local-backups/before-historical-posting-20261026T162738/
database.sqlite3 (directory 0700, file 0600, integrity check OK). Migrations were applied
only to isolated QA/test databases. The normal production database was not changed.

## Validation

All 271 finance tests passed on PostgreSQL, including historical selection/origin,
exact-overlap and uncertain matching, repeated/equal rows, both upload orders,
classification conflicts, cross-account duplicate/stale-plan rejection, copy scope,
optional date filters, reviewed/reconciled protection, audit and undo. Migration drift
check passed. Changed frontend files lint clean; production build passed.

Browser verification used a synthetic four-row workbook only: one classified debit,
one September credit, one explicit cash credit and one invalid row. Exactly two bank
movements were posted. Records preserved description, category/subcategory, studio,
expense month and review state. Reopening the workbook showed its active import and
both August/September dates. Original field inspection and final confirmation were
captured locally. Synthetic preview 7, derived batch 18 and movements 359/360 were then
removed with guarded fixture-only cleanup; account token advanced. Real preview 6's
company/hash/327 rows/original bytes were checked unchanged. It has zero derived bank
imports, and the local bank ledger remains empty for the client's own replay.

Local QA restored: backend 8027, frontend 3037; temporary PostgreSQL test cluster stopped.

## What the client should test

1. Refresh Historical migration, choose Migration preview QA and Review / import the
   existing workbook. Confirm all dates and debit/credit tabs are clear.
2. If using the existing Popular setup, explicitly copy the preview to QA financial
   company. Otherwise configure the intended bank account in the original company.
3. Choose the operating account, select only rows actually paid through it, exclude
   cash/manual non-bank entries, confirm origin, review the import and confirm posting.
   Cash and the invalid row should remain pending. September 1 must be included.
4. Open Records and check descriptions, expense months, studios, methods, terminals,
   categories/subcategories and Not reviewed queue. Unmapped configuration stays pending.
5. Upload routine September bank reports to that same company/account. Check overlap
   links and explicitly review uncertain matches before resolving them. Do not expect
   cash posting, reconciled balances or a final monthly result from this delivery.
