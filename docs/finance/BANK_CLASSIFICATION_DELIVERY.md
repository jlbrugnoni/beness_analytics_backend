# Bank records: classification/edit dialog

Date: 2026-10-26. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. No push/merge/deployment.

## Scope and business behavior

Client accepted the first daily workspace and requested bank debit/credit editing
next. Existing import readers, source identities, overlap/correction review and
posting logic are retained. One new optional BankMovementClassification record
holds business assignments separately from the reported source and fingerprint.
Migration0012 creates this structure; no source backfill or automatic guesses.
Applied only to isolated QA/tests; the normal/production database was not migrated.

Records → Bank debits / Bank credits → Edit opens the new dialog. Both directions
allow manual description/concept, studio or company-wide
Administration, payment method, terminal, movement kind and recognition/review flag.
Debits additionally allow category/subcategory and expense month; credits allow operation date. Source bank
date, amount/currency, reported balance, original description/references and account
are protected. Bank source corrections still use the existing explicit review flow.
The two dates/months are independent. YYYY-MM expense month saves as its first day;
operation date is YYYY-MM-DD. No expense period is guessed from a payment date.

The month/date controls use validated text input with explicit examples. Browser
verification caught native date/month fill values not persisting through form
updates; final controls were retested through save/read-back. Backend DateField
validation also rejects impossible dates and expense-month days other than1.

Category/subcategory must belong to the movement's company and correct hierarchy.
New assignments require active categories/ancestors; existing inactive references
can remain while another field is edited. Studio must belong to the company site, the user’s allowed scope and any explicit
account studio participation;
Administration is explicitly company-wide and cannot coexist with a studio.
A partial-studio grant cannot assign company-wide administration.
Terminal must belong to this exact bank account and agree with assigned studio and
channel. Selecting a terminal fills its configured studio/channel. Changing studio
or method clears terminal visibly. Existing inactive terminal evidence is retained.
Configuration is editable through existing settings, not hardcoded bank categories.

Movement kinds: customer receipt, expense, internal movement, bank/processing fee,
fee reimbursement, refund, extraordinary. Income-only and expense-only types are
validated against bank direction. These are assignments for later workflows, not
creation of sales, counterpart transfers, refund allocations or calculated results.
Administration does not create an allocation or an artificial studio. Current
operational/extraordinary category defaults and later result semantics are not
redefined by this editor.

Recognized/reviewed is independent from classification completeness and actual
reconciliation. Partial assignments can be saved. Needs review remains when type,
relevant category/subcategory/expense month, studio/administration, receipt method/
operation date or review flag is missing. A reviewed record can still need
information. Internal movements do not require fabricated expense categories or
sales-operation dates. The editor cannot set reconciled or create a settlement.
Credit category/method filters show missing factual assignments even when those
fields are optional for a particular kind; they do not imply missing expenses.

Workspace tables display assignments alongside original facts and support server-
side category/subcategory/studio/method/search filters, Needs review, Missing
category, Missing payment method, Reviewed and Not reviewed. Filter counts/amounts
apply before pagination. Source amounts remain unchanged. Category names and other
related labels remain human-readable; company/account and sensitive-detail scopes
still guard data, filters, options, histories and aggregates.

## Guarded edits and preservation

GET bank-movements/{id}/ returns source, classification, completeness and edit state.
GET bank-movements/{id}/options/ provides scoped catalog/studio/terminal choices
without requiring financial-settings permission. POST .../assign/ accepts only
business assignments, expected revision and optional comment. Unknown source-fact
keys (amount/source/date/reconciled etc.) are rejected explicitly.

Reuse company → account locks plus movement row lock, scope/sensitive access and
existing can_edit_finance capability. No new grants or parallel roles. Inactive
company/account/record or reconciled movement cannot be edited; stale saves fail409.
Classification updates advance movement revision and account ledger revision.
BankEvent classify stores actor/optional comment and complete before/after assignment/source
snapshots. Existing source and fingerprint are not overwritten. Reupload/overlap
links the same movement, retaining assignments; approved source correction also
retains them. Existing undo protects revised/edited and reconciled records.
Foreign keys protect used categories, studios and terminals from deletion.

The old verbose button label is now **Import details** / **Detalles de importación**.
It still navigates to source-specific review/undo/history; navigation alone never
imports or reverses financial records. Contextual existing URLs remain unchanged.

## Validation and concrete QA state

- PostgreSQL: all322 supported finance/analytics/purchase/import-guard tests passed.
- SQLite:322 discovered;316 passed,6 existing PostgreSQL-only tests skipped.
- Nine new classification tests cover separate source/assignments, expense-month
  independence, audit/revision, source-fact protection, category hierarchy, foreign/account/partial-studio
  scope, terminal consistency, incomplete-review behavior, query filters/totals,
  review versus reconciliation, grants, stale/reconciled edits, reimports, approved
  source corrections and protected undo. Existing workspace filter test updated
  because bank studio filtering is now implemented.
- Frontend lint/build and Django system/migration consistency checks passed;
  existing unrelated frontend warnings remain. Logs:
  /private/tmp/finance-bank-edit-{focused,regression,pg,lint,build}.log.
- Synthetic company6 / account5 Synthetic bank editing QA: created two synthetic
  posted movements from bank-edit-synthetic.csv, debit355 /-20DOP dated Sep2 and
  credit354 /100DOP dated Sep1. No real report was posted or source edited.
- Synthetic debit355 saved description Synthetic August electricity, category111
  Synthetic services /subcategory112 Synthetic electricity, Receipt Studio QA,
  Transfer, expense month2026-08 and reviewed. Its source remains Sep2/-20DOP.
- Synthetic credit354 saved Customer receipt, configured terminal9 SYNTHETIC-EDITOR,
  Cierre, Receipt Studio QA, operation date2026-08-30 and reviewed. Source remains
  Sep1/100DOP. Both now have no completeness reasons and are unreconciled.
- Browser exercised choices, edits, date save/read-back and independent status
  updates in the real UI against isolated QA. Screenshot synthetic only:
  /private/tmp/finance-bank-edit-dialog.png.

## What you should test

Open http://127.0.0.1:3037/finance/records?company=6 using the existing QA credentials.
Receipt posting synthetic QA is test data; account Synthetic bank editing QA holds
safe examples. Do not confuse it with the company holding real historical previews.

1. Bank debits → Edit: inspect the classified20DOP example. Change manual concept,
   category/subcategory, studio/method or expense month (YYYY-MM), optionally enter a comment,
   Save. Close/reopen and verify; bank date/amount/reference remain unchanged.
2. Bank credits → Edit: operation date differs from deposit date. Select the
   synthetic terminal and verify studio/Cierre; inspect original report fields.
3. Change category and confirm subcategory clears; choose an appropriate child.
   Save incomplete work deliberately; Needs review identifies what remains.
4. Recognized/reviewed does not mark Reconciled. Inspect separate filters and
   Correction history. Category/manual-description filters include these records.
5. Import details opens the existing detailed source screen. No undo/import occurs
   merely by opening it. Reimport overlap preservation is covered by automated
   tests; use synthetic source for additional manual posting/undo tests.

## Remaining boundaries

No manual cash creation/deletion/void permissions, shared expense allocation,
actual bank-to-sales reconciliation, purchase/Egreso matching, results, historical
financial migration or production rollout is added. Those remain separate stages.
Existing real historical/raw source previews are unchanged. Future migration should
write these same assignment structures with explicit provenance/conflict review,
not a separate table of financial facts.

## Follow-up: routine comments and movement type help (2026-10-26)

Client reported the mandatory reason obstructed routine completion. Bank assignment
comments are now optional in API and dialog; omitted/blank comments still produce
actor/time/before/after audit events and revision increments. Empty-comment history
shows a translated Classification updated label. Explicit source-review/undo reasons
and invoice/receipt correction reasons remain required. No schema change.

The movement selector now explains each kind in English and Spanish. Type answers
why money moved; method answers how. Electricity paid by transfer is Expense +
Transfer; own-account transfers and deposits of cash already recorded are Internal
movement + Transfer. These descriptions reflect agreed management policy; actual
reconciliation and monthly results remain future deliveries.

Validation: focused bank classification/posting suite: 30 found, 28 passed, 2
PostgreSQL-only race tests skipped on SQLite. Includes omitted/blank comments,
audit/revisions and retained source-review/undo reason requirements. Changed-file
frontend lint and production build passed.

Client check: edit debit/credit classification with Comment left empty, save and
reopen; inspect history and movement-type help. Source bank facts stay read-only.

Browser QA: synthetic company6/debit355 saved an updated description with an empty
comment. UI confirmed Changes saved and history showed Classification updated with
before/after values. No real records changed. Screenshot:
/private/tmp/finance-optional-comment.png. Local backend8027/frontend3037 restored.

## Follow-up: debit-only categories and terminal recognition (2026-10-26)

Client clarified expense categories/subcategories do not belong on bank credits.
Credits now omit category columns, filters, missing-category status and dialog fields.
The API returns no credit category options and rejects new credit category assignments
and category filters. Existing legacy assignments are not silently deleted. Expense
classification remains available on debits; credit studio/method/operation date and
manual concept remain editable. Protected source facts and optional comments remain.

Root cause: terminal selection populated studio/method only after manual selection;
posting never interpreted the configured terminal identifier in bank descriptions.
New posted credits (including explicit reviewed creates) now match complete terminal
identifiers in description/short_description to active mappings for that exact bank
account, company/site, account participants and importing user's studio scope. Exactly
one eligible match fills terminal, studio and channel. Patterns are loaded once per
import/account operation. No substring/prefix guesses, source rewrites, fees, sale
classification, operation-date inference, recognition flag or reconciliation inferred.
Caixa terminal plus DDMM is recognized as a terminal; date inference remains separate.

For existing records: Records → Bank credits → Apply terminal mappings to existing
credits, POST workspace/recognize-terminals/ {company}. The UI explicitly states this
checks ALL company credits, independent of table filters. Whole-company workspace,
full-account, money, bank, edit and sensitive-detail access remain enforced. The action
uses company→account→movement locks within a transaction, fills only compatible
unreviewed credits, records before/after + actor/time + automatic-match note, increases
movement/account revisions, and is idempotent. Reviewed/reconciled/inactive rows,
existing terminal assignments, administration, non-receipt kinds, conflicting studio/
method and unknown/multiple matches are preserved. Correcting a source does not erase
manual classification; older overlapping rows are recognized using this explicit
catch-up action rather than covert writes during GET. No new schema migration.

Validation: PostgreSQL44 focused classification/posting/workspace tests passed;
SQLite42 passed/2 PostgreSQL-only skips. New cases cover Popular, Caixa, exact token
boundaries, unknown/inactive/multiple/foreign-account terminals, manual conflicts,
review protection, permissions, audit/idempotence, overlap and debit-only categories.
Changed-file frontend lint and production build passed. Browser synthetic company6:
movement356 QA-AUTO-901 recognized SYNTHETIC-EDITOR/Cierre on posting; movement357
QA-RETRO-902 imported before mapping existed, then catch-up updated exactly1 credit
to SYNTHETIC-RETRO/Recurrente/studio7. The existing reviewed credit stayed unchanged.
Dialog and table contain no expense categories. Screenshot:
/private/tmp/finance-credit-terminal-recognition.png. No real source/record/grant edits.

Client checks:
1. Refresh Records; credits have no category/subcategory fields, columns or filters;
   debits retain them.
2. In the intended company, apply terminal mappings once for older credits. Open a
   recognized AZUL record and compare its terminal, studio and method with Settings.
3. Upload a new bank report: a known account terminal should fill automatically.
   Unknown/multiple identifiers and conflicting prior assignments stay for review.
4. Repeat catch-up: already assigned credits remain unchanged. History records the
   automated assignment. Dates, amounts and bank references remain protected.

Both repositories remain local feature/finance-phase-2; client acceptance pending.
No production migration, merge, push or deployment.

## Follow-up: compact dialog and completion-based review (2026-10-26)

Client requested removal of the persistent source-read-only banner and missing-data
summary alert. Removed both; source fields remain protected. Original report details
now open from an accessible, tooltip-labelled info icon beside the transaction header.
Required empty fields are marked directly with a red border, asterisk and local helper
text, updated as the user changes movement kind, category or assignments.

Reviewed is now a completion gate for the daily unprocessed queue. Applicable rules
remain: movement kind; studio or administration except internal principal transfers;
debit Expense/Fee/Extraordinary needs category, an active child subcategory if the
parent has children, and expense month; customer receipts need method and operation
date. Optional descriptions, comments and terminals are not required just to complete
a row. Terminal is optional for cash/transfers. Existing type-specific exemptions are
preserved; internal movement does not require a fictitious expense category/studio.

The checkbox is disabled while required data is missing or date/month input is invalid.
Incomplete work can still be saved without checking it. Removing required information
clears the review flag in the dialog and on the server. API attempts to explicitly set
reviewed=True while incomplete are rejected before writing. Updates that leave required
data missing store reviewed=False, with the normal revision/audit. Recognition remains
separate from reconciliation. No source edits, schema changes or automatic review.

Shared backend missing_fields rules drive detail completeness; reviewed/unreviewed
workspace SQL uses matching requirements. Legacy incomplete reviewed flags are shown
and filtered as unreviewed without silently updating rows on GET. No data migration.
Not reviewed is the existing Status filter for daily unfinished bank records; the
filter default remains All until the user selects their work queue.

Validation: PostgreSQL46 focused classification/workspace/posting tests passed;
SQLite44 passed/2 PostgreSQL-only skips. Tests cover rejected incomplete review,
partial saves, clearing review when required data is removed, legacy pending flags,
complete recognition and existing import/terminal/permission/audit protections.
Changed-file frontend lint and production build passed. Browser company6 synthetic
credit357: saved customer-receipt kind without date/comment (still pending), filled
operation date to enable checkbox, checked then cleared date to verify automatic
uncheck/disable, restored date2026-09-02 and saved reviewed. Not reviewed queue now
contains only unfinished credit356; completed357/354 excluded. Info icon opened the
original source table. Real records and permissions unchanged. Screenshot:
/private/tmp/finance-review-required-fields.png. Local backend8027/frontend3037 running.

Client tests: refresh; open an unfinished credit/debit and inspect direct field marks;
verify info icon; save partial work; complete marked fields and check Reviewed; remove
a required value and verify review clears; use Status → Not reviewed → Apply filters
as the daily queue. Completion does not mean bank reconciliation.
