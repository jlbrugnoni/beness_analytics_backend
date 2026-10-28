# Finance screen and workflow specification

Status: Phase 0 accepted, 2026-10-24. These describe the target screen flows.
Phase 1 implements finance landing, group capabilities and user grants/effective
access. Phases 2.1–2.4 implement company/account/terminal/category/source-mapping and
fee/timing/tax configuration with previews. Bank previews/history now exist (Phase 3.1); bank transaction commit/review/undo now exist (Phase 3.2); sales imports,
classification and results remain future work. Phase 3 discovery is recorded in PHASE_3_DISCOVERY.md.

## Entry and setup

Finance navigation requires financial view, money visibility, and appropriate
location scope. Expose only available actions. Add group capability editing and
effective/inherited permission display in existing user management.

Configuration flow: company -> account -> terminals/studio mappings -> editable
categories/subcategories -> source/payment/fee/tax rules. Start DR with the
recommended Banco Popular operating-account label; leave setup values editable.
Mark sensitive categories and define operating/extraordinary/shared treatment.
Use real source layouts without committing private financial files to Git.

## Imports

Choose routine source import or historical migration, then company/account/source.
For migration, map existing enriched columns and match existing studios; propose
missing configuration for confirmation. Show preview counts/totals and issues.
After commit, show imported/updated/unchanged/pending rows and links to their review
tasks. Preserve the original file name, batch, raw row, and history.

Popular reader handles two debit/credit sections. Caixa reader handles signed
EUR values. Alegra reader groups invoice items and counts invoice totals once.
Spain uses already imported Mindbody Sales through an adapter; finance does not
ask for a duplicate routine sales upload. Future Spain Alegra adoption requires
one authoritative source/cutover and validation of unnamed consumer invoices.

Reupload, reordered rows, partial periods, and manually entered bank records must
not duplicate genuine movements. Missing rows in a later partial file are not
deletions. Invalid/ambiguous records remain reviewable while independent valid
records import. Import commit rechecks stale preview/source versions.

## Manual entry and review

Income/Expenses provide Create manually and Import report actions. Manual entry
sets account/company, date, amount/currency, description, kind, and relevant
period/studio/channel/category. Show missing optional assignments as review work
rather than fabricate values. Keep Manual/Imported/Migrated labels visible.

Review table: bank date, operation date or expense period, amount, business
description, studio/channel/category, origin/report, and separate review/match
statuses. Open record to view original versus assigned fields and history.
Imported records edited manually retain original origin. Bulk editing checks all
affected rows' scopes and stale versions, not only the table filter.

Sensitive categories display authorized category totals but no individual payment
rows or identifying details without the extra capability. Protect searches,
history, match candidates, exports, and raw files as well as screen text.

## Internal movement and fee reimbursement

Own-company cash deposits and operating-to-savings transfers remain bank/cash
movements outside sales/profit. Assign source/destination and link counterpart
when available. Unimported savings counterpart stays pending; do not create a
verified destination balance. Charges associated with transfer remain expenses.

Caixa fee reimbursement is a different kind: keep the fee debit and reimbursement
credit, link the reviewed offset, and show both without treating reimbursement as
a sale. Unknown AZUL fees are review items; do not assume they are additional
withholding or ignore them to improve reconciliation.

## Reconciliation and refunds

Select company/studio/period/channel. Compare source sales with expected fees and
net receipts assigned by operation date. Drill into sales and bank movements;
suggest grouped/partial matches. Users confirm, split, or leave unresolved with
notes; every nonzero difference remains recorded, including rounding candidates.

Refund entry/source update links to the original sale and adjusts its result
month. Actual returned money stays on its bank date/channel. Missing original
sale stays for review. Avoid applying both source cancellation and refund as two
reductions. Show the affected original month and revised administration weights.

## Administration and monthly results

Company-wide administration costs retain original category and expense period.
Preview allocations from that month's company gross sales including IVA before
fees. Show studio income, weight, and allocated amount only where authorized.
Restricted studio filters do not alter company-wide denominator calculations.
No-income month stays pending with manual split available. Apply deterministic
rounding so allocated amounts sum to the original expense; store provenance.

Monthly results show gross sales, processing fees, direct operating costs,
administration, operating result, extraordinary inflows/outflows, and final
management result. Drill-down respects sensitive detail and location access.
Company total never adds shared parent expense and allocation children together.
Explain income/expense source coverage; Spain expense-only historical periods
are incomplete, not evidence of a completed loss.

Initial v1 allows audited corrections; no mandatory Close month gate. Later
closing and net-of-tax reporting are separate enhancements. Do not describe
the custom final management result as EBITDA.

## Export and configuration changes

Exports require their own action permission and the same location/detail rules
as API views. Exports and original source downloads are different permissions;
sensitive raw files cannot bypass category-detail restrictions.

Renaming categories keeps existing references. Changing rates/mappings/tax defaults
does not silently restate historical records. Show affected periods before an
explicit recalculation and retain earlier values. Used configuration is archived
rather than deleted. Action audit is required throughout.

## Implemented category setup

In Financial configuration -> Categories, choose a company. For an empty catalog,
Use starting catalog creates the common approved baseline once. Alternatively,
start manually; an existing manual catalog cannot be overwritten by initialization.
Add category and Add subcategory support two levels. Rename/deactivate records
while retaining identity; company/parent reassignment and hard deletion are blocked.

Display own versus inherited privacy/defaults and effective inactive state. A
category settings manager without sensitive-detail access can edit ordinary
categories; protected-category and sensitivity controls remain unavailable.
Changing defaults is not historical reclassification. See PHASE_2_2_DELIVERY.md.

## Implemented mapping setup and tests

In Financial configuration -> Source mappings, select company, then add an exact
source-field/value alias to a channel or studio, leave for review, or mark a price
list neutral. DR setup proposes the three explicitly selected existing studios
and adds missing agreed aliases without replacing existing choices. Spain method
labels are entered from actual source evidence, not guessed from DR conventions.

Test mappings accepts reported values and optional manual choices. It shows
assignments/origins/review state plus source warnings. It does not upload reports
or save financial corrections. Recurring can be selected manually to override a
Tarjeta crédito -> Cierre suggestion; source evidence remains visible. See
PHASE_2_3_DELIVERY.md for accepted defaults and client steps.

## Implemented bank preview flow (Phase 3.1)

Finance -> Bank report previews -> choose a supported bank account and format ->
select raw CSV -> Save bank preview. Show immutable account-specific history and
valid-row totals/issues. Select a batch to inspect transaction, invalid or all
source rows; Source cells retains original values. Original CSV download uses a
protected authenticated endpoint. Repeated upload is another preview, linked if
its bytes match; no transaction count changes because no posting exists yet.

Full bank-account scope and sensitive-detail capability guard all raw history/
rows; import capability additionally guards saving/retrieving originals. No
settings permission is required for an appropriately scoped importer. Read-only
users with the detail grants can inspect history without uploading/downloading.
No Commit, Reconcile or Undo action is presented in this delivery. See
PHASE_3_1_DELIVERY.md for boundaries and the next step.

## Implemented transaction import/review/undo flow (Phase 3.2)

Open a bank preview -> Transaction import and review -> inspect counts/decisions
-> Import transactions -> confirm the concrete plan. New unambiguous movements
post; recognized occurrences link; invalid and ambiguous/correction rows remain
without fabricated transactions. The uploaded source and its original totals stay
unchanged. Financial status appears separately in upload history.

Review a pending row -> compare reported and existing source -> choose distinct
new transaction, keep existing/link, approve bank correction, or ignore -> enter
reason -> confirm. Scoped ID lookup can select a target beyond the first 50
suggestions. Stale account/row/movement context requires reload. History retains
old/new bank values. No expense/studio/date assignment is implied by posting.

Preview undo -> inspect eligible/protected/reused counts -> enter reason and
confirm -> eligible creations reverse, protected/reused records stay, source files
and history remain. Partial undo ends pending resolution for that posting. A fresh
undo preview may later reverse newly eligible records after dependencies clear;
it cannot force edited/reconciled/corrected values back. Undo ownership follows
the financial committer; managers require the same import/edit/detail/account
permissions. Expand Account transactions and history for active/all/reversed
records and readable before/after events. See PHASE_3_2_DELIVERY.md.

## Implemented Alegra sales posting — Phase 3.3.2

Save source preview, review invoice/item validation, then explicitly Import sales.
Complete independent new invoices post; unchanged invoices link to current sales.
Unknown/invalid invoices require corrected source; unexpected changed facts stay
pending for investigation and can be retained with a reason. No partial invoice
item posting or missing-row deletion.

Review a later Anulada status before approving cancellation. Keep original sale
facts and choose separately refund expected/no refund/replacement with a note.
A replacement must be another active paid invoice in the company. No bank debit
or second profit deduction is generated. Manual studio/recurring corrections and
all before/after evidence survive overlapping uploads. Refund-to-bank matching,
expense classification and period results remain later deliveries.

Undo previews eligible/protected/reused invoices. Only untouched creations reverse;
manual/reconciled/dependent/approved-cancellation records remain protected. All and
Reversed views retain history. Undo does not delete immutable source uploads.

## Implemented enriched workbook preview — Phase 3.4.1

Choose Dominican company, pilot month and native XLSX. Save a private source
preview, then inspect transaction/operation/expense-month totals, known manual
fields and raw cells/formula caches. Unknown bank/cash provenance and saved errors
are review issues. All entries includes incomplete rows. Empty checkbox template
rows do not become movements. Reupload records source lineage, without posting
financial transactions. Financial migration decisions and complete-month
comparison remain Phases 3.4.2–3.4.3; updated sources are present in the local app
as documented in SEPTEMBER_ALEGRA_COMPARISON.md.


## Proposed paired invoice/payment uploads (D-065)

Recommended sequence: original invoice/item report → original payment report →
bank reconciliation. Bank uploads remain independent and can precede either.
Missing counterpart creates a visible pending link, never a fabricated invoice,
receipt, studio or settlement. Exact eligible links are rechecked when counterpart
financial records are posted. Repeated/overlapping source files preserve identities,
manual corrections and evidence. Native payment importer is not yet available;
ALEGRA_DUAL_REPORT_IMPORT_PLAN.md defines discovery and delivery sequence.


## Implemented workbook payment source inspection — Phase 3.3.3.1

Open an existing migration workbook preview, then Show Alegra payments. Inspect
payment month or All payment dates, filter by full invoice code or review issues,
and open Payment source cells. Original Asociaciones provides the invoice reference
when derived NCF is blank. Split payment occurrences remain separate; group totals
span all payment dates in this workbook. Source assignments/flags are retained,
not confirmed receipt/invoice/bank links. No financial record is created by this
read-only panel. See PHASE_3_3_3_1_DELIVERY.md for the client test checklist.


## Implemented shared payment imports — Phase 3.3.3.2

Routine: Finance → Payment imports → upload CSV matching the observed payment
column contract → inspect source, new/reused/conflict/invalid plan → confirm Import
valid payments. Historical: initial setup → existing workbook → payment preview →
Prepare shared payment import → same review/commit screen. Preparation uses chosen
payment-date scope, not invoice/review search filters. Initial setup is not required
for subsequent CSV uploads. Unknown native layouts retain a clear source error.

New valid receipts link eligible exact invoices or wait visibly for them. Invalid
source identities do not block other receipts. Conflicts offer audited Keep current
payment; replacements are not silently approved. Current payment methods can be
edited with a reason; later raw sources cannot erase them. Undo preview preserves
edited/reconciled/reused/supported receipts; sale undo protects active receipt links.
No bank settlement or extra revenue is created by receipt posting.


## Corrected routine payment format (D-069)

Finance → Payment imports → original Alegra payment XLSX → source preview →
review/confirm valid payments. XLSX is the normal format; optional CSV support
remains. The worksheet is detected from the observed payment columns, with title
rows allowed. No enriched master, migration page, manual columns or conversion is
required. See PAYMENT_XLSX_CORRECTION.md for verification and limits.


## Client workflow correction: daily tables (D-071)

The client finds the separate import-centered screens too complex for daily work.
Target one Upload page and a separate cross-import Records workspace with bank
debit/credit, invoice/item and customer-payment tables, filters and Edit dialogs.
Manual assignments are follow-up work, not an import prerequisite. Keep original
facts separate and locked, preserve source evidence, and move migration/setup out
of routine navigation. DAILY_WORKSPACE_PLAN.md supersedes the proposed navigation
above where they conflict; older implemented-flow descriptions remain delivery
history, not evidence that the new workspace has been built.


D-072 refines D-071: use three primary Records tabs, Bank debits, Bank credits and
Invoices. Both Alegra reports enrich the invoice table; invoice dialog shows items
and zero/one/many linked payments, with permitted method/studio correction there.
Unlinked payments remain in a secondary review view. Imported amount/number/client
are read-only as explicitly confirmed by Q-018; source updates use reviewed report
changes. DAILY_WORKSPACE_PLAN.md contains the proposed inheritance/override design.


First D-071/D-072 UI delivery implemented: Finance now opens Records with three
primary tabs, one Upload page, invoice/items/linked-payment edit dialogs and a
secondary unlinked-payment view. Existing import/identity/review/undo services
remain; an audited receipt studio override/inheritance complements the method
editor. DAILY_WORKSPACE_DELIVERY.md is authoritative for delivered scope and client
tests. Broader bank classification/manual creation and later workflow UI remain
unfinished; source recognition does not imply bank reconciliation.


## Implemented bank assignment dialog — 2026-10-26

Records → bank debit/credit → Edit now supports manual classifications, business
concept, company-scoped category/subcategory, studio/administration, method/terminal,
kind, separate expense month/operation date and recognition flag. Source facts stay
locked. Incomplete work can save, with separate completeness/review/reconciliation
states; reasons and before/after actor audit remain. The existing overlap and source
correction services preserve assignments; undo protects revised records. Import
details is the shortened label for the unchanged source review/undo/history screen.
BANK_CLASSIFICATION_DELIVERY.md is authoritative for delivered scope and client tests.

## Monthly closures comparison — C-1 (D-085)

Open Finance → Closures, select company and month, optionally studio. Each payment
method shows expected receipts (Alegra payment amounts less estimated withholding),
actual recorded bank/cash receipts and actual-minus-expected difference. Click the
method for all calendar days, monthly totals and accumulated difference; click a date
for source records, toggling All/Alegra payments/Actual bank-cash. Review unresolved
assignments and excluded internal/refund/extraordinary credits through their queues.

Use Records to correct business assignments and then refresh Closures. Source facts
remain protected. One actual receipt has one operation date; no deposit splitting.
Opening a comparison or a zero difference never confirms reconciliation. Unknown
fees remain —, and source coverage is not certified. DR is available first; Spain's
Mindbody bridge and explicit saved confirmations remain later work. See
MONTHLY_CLOSURES_DELIVERY.md for the exact calculation and client acceptance steps.
