# Daily finance workspace: client workflow correction

Date: 2026-10-25. Client requirements recorded in D-071–072. The implementation
sequence and permission/deletion recommendations below are proposed, not delivered.
No runtime or financial records are changed by this document.

## Problem confirmed in the current implementation

Finance landing exposes separate bank, sales and payment import destinations,
configuration and a migration section, followed by company cards. Synthetic QA
companies appear alongside client working data. Bank records are embedded in an
import posting panel; sales and receipts have separate lists embedded in import
screens. The bank movement API is read-only and has no full expense-assignment
editor yet. Existing sale studio/channel and receipt channel edits cover only
part of the client's daily review needs. These are real workflow gaps, not a
request to make the client complete every assignment before importing.

The client uses Excel tables directly, expects one or two initial migrations,
then frequent reports for two companies. Daily import should update shared
operational tables, not require users to navigate batches to find their records.
Raw rows, operational records and issues remain distinct internally; the UI must
make their relationship understandable without exposing implementation terms.

## Target navigation

- Records: default day-to-day destination with one company selector and three tabs:
  Bank debits; Bank credits; Invoices. Linked customer payments (Alegra_adm)
  are displayed and edited inside the invoice dialog, not a fourth main tab.
  Use business labels; explain report names as source labels. Do not call all
  bank debits expenses or all bank credits sales: transfers, fees, reimbursements,
  refunds and other movements remain visible with their own treatment.
- Upload reports: one page, one consistent preview/confirmation workflow, with
  upload history as a secondary tab/section. Report types depend on company and
  supported source policy; account selector appears for bank reports only.
- Settings: accounts, terminals, categories, mappings, fees and company rules.
  Historical migration is secondary initial setup, retaining access to originals
  and prior previews rather than being part of the daily upload sequence.
- Reconciliation and Results are added when delivered. Do not show completed
  reconciliation/result functionality or badges based only on import/recognition.

Reuse the Analytics import screen's company/report/file/preview pattern and the
application's table styles. The design applies to both companies, while source
adapters remain constrained by verified formats. Spain still uses Mindbody sales;
no routine Alegra switch or duplicate Mindbody upload is implied.

## Daily upload workflow

1. Choose company, report type and account if relevant, then select original file.
2. Show recognized source, filename, actual date coverage, row count and source
   totals in its own currency. Display one preview table with readable dates,
   names and amounts; Source opens original fields/cells in a dialog.
3. Show new, existing, conflicting, invalid and out-of-scope rows in understandable
   terms. An Alegra Egreso is an out-of-scope purchase in this payment importer,
   not a defective purchase. Preserve it in source evidence (D-070).
4. Confirm import of valid records. Missing category/subcategory, studio, operation
   date, expense period or method review is subsequent work and does not prevent
   an otherwise valid independent record from becoming operational.
5. Show imported/existing/pending counts and a direct View records action filtered
   to records supported by this upload. All records remains available across
   uploads. Pending source conflicts and unreadable rows remain accessible too;
   never manufacture IDs or amounts merely to populate an operational table.

Bank debit/credit are table views, not necessarily separate files. Popular's
verified export has both sections; Caixa's verified export has both directions.
Never require the user to split a combined source to fit the UI. Q-017 answer confirms three Dominican uploads: combined Popular bank report,
Alegra transactions/payments, and Alegra invoices/items. Debit/credit and invoice
tables are views, not mandatory separate files. Both Alegra reports feed the one
invoice workspace without merging their distinct invoice and payment identities. Do not ask the client to split bank directions.
Spain retains its already agreed Caixa bank and existing Mindbody Sales source
policy; no additional mandatory report or Alegra cutover is inferred.

## Operational tables and editing

Tables query all authorized operational records independent of selected source
batch, using server-side filtering, ordering and pagination. Filters combine and
apply before pagination and totals. The same company/studio/account and sensitive
scope guards apply to queries, counts, dropdowns, source dialogs and histories.
Use concise toolbar filters (period, account, studio, status, search) and relevant
column filters (category/subcategory/method etc.). Include origin and report links.
An upload filter identifies all linked records including reused ones, not only
records originally created by that batch. Preserve filters/page on modal close.

| Table | Main source columns | Business fields / actions |
| --- | --- | --- |
| Bank debits | Bank date, description, amount, currency, reference, reported balance where present | Manual description, expense month, category/subcategory, studio/administration, movement treatment, recognition/review, source/history |
| Bank credits | Bank date, description, amount, currency, reference, reported balance where present | Operation date, payment method, terminal, studio, manual concept, movement treatment, recognition/review, source/history |
| Invoices | Invoice code/date/client/status/total/studio; payment count and payment-method summary; status/review | Open invoice dialog for items, one or many linked payments, permitted studio/payment-method edits, source/history and reviewed cancellation flow |

Use Edit dialog, not inline mutation. Show Original report and Editable business
fields separately. Imported code/number, source dates, amount, customer identity,
original description/status and item facts are locked. Operation date and expense
month are separate editable assignments; editing them does not alter bank date.
Actual source-fact changes use existing explicit correction/cancellation flows.
Save requires revision checks, audit and validation against active same-company
configuration. Manual assignments survive overlapping raw imports and blanks.
Invoice client/date/amount are not manually rewritten to force reconciliation.

Recognized/reviewed, classification completeness, method review and reconciled
are independent indicators. Provide All, Needs review, Missing classification,
Payment method review, Unreconciled and Reconciled views as their underlying
behavior is implemented. Do not advertise a functioning reconciled filter based
on a legacy checkbox or unsupported matching model. A record can have several
pending reasons. Unknown information stays visible rather than being guessed.

## Invoice-centered workspace (D-072)

Both Alegra reports enrich one invoice table. Keep invoice/item and customer-
payment records, identities, dates, original amounts and provenance distinct.
An invoice row displays its number, date, client, invoice total, effective studio,
payment-method summary/count and meaningful review/link status. Invoice totals
are counted once regardless of item or payment count. Multiple methods can be
summarized as Mixed with details in the dialog; never choose one arbitrarily.

Click an invoice (with an explicit keyboard-accessible Open/Edit action) to open
one dialog containing:

- Invoice header and studio assignment; source identity, date/client/amount/status
  remain read-only in ordinary editing.
- Original item detail, available without a separate primary table.
- Linked payments. For one payment, display its fields directly without a second
  selection step. For several, display each distinct payment and its edit controls
  in the same dialog. For none, show Waiting for payment report; do not create a
  full-amount payment or infer collection merely from the invoice row.
- Original reported payment number/date/amount/client/method/account and the
  current corrected method/studio, visibly distinguished. Keep source evidence
  and audit accessible without leaving the invoice context.

The client explicitly wants payment-method and studio corrections in this dialog.
Preserve separate invoice studio and payment studio assignments: use the invoice
studio as the default when no payment-specific override exists. A payment studio
correction affects that payment, not every sibling payment or the immutable cost-
center field. An invoice studio correction updates its assignment; it propagates
only to payments still inheriting the invoice studio. Explicit overrides survive
later imports and invoice edits. Show From invoice versus Manual override and
mismatch review clearly. This assignment behavior is the implementation design
for the requested editing workflow, not an existing delivered receipt capability;
the current receipt editor only changes payment method.

Q-018 answered: invoice/payment amounts, identifiers and client details are
read-only; source changes must arrive through a newer report and the existing
source-change review flow. Do not enable manual mutation of these facts or silently
overwrite them on reupload. Existing cancellation/immutable-fact contracts still
apply; this answer does not authorize arbitrary source replacement or identity
merging. Method/studio overrides are business assignments and retain history.

Keep payments awaiting an invoice, cancelled/conflicting invoice links and source
exceptions accessible from a Needs review / Unlinked payments view within this
workspace, with payment detail/edit access where allowed. They cannot vanish just
because the main table is invoice-centered. This is a secondary review view, not
a fourth primary Records tab. It must also support payment-before-invoice imports
without generating placeholder invoices. Posted payments, pending source rows and
out-of-scope purchases remain clearly distinct.

Payment sums/link coverage are not bank reconciliation. A single linked payment
may be partial; never label an invoice bank-reconciled solely because it has one
payment or its linked payment total equals the invoice amount. Use the actual
stored link/coverage state and later bank-match model for their respective labels.

## Manual creation and permissions: recommendations

Place Create manually on the applicable Records table, not only an import page.
Start with agreed manual cash/movement support. A manual entry carries its own
identity and Manual origin; never impersonates an Alegra invoice/payment number
or a reported bank balance. Manual edits to imported entries retain their origin.

Retain existing user/group OR grants and site/studio/money/sensitive gates.
Existing import and edit capabilities remain separate. Add explicit, independently
assignable create-manual and void/archive capabilities, with per-record-kind gates
where the client needs them, to the existing editor rather than separate roles.
Final permission names/matrix are implementation discovery, not current grants.
Do not grant new actions automatically to existing import/edit users.

Recommend audited Void/archive + reason for permitted operational records,
preserving source/history and dependency safeguards. Imported records must not
have ordinary hard deletion. Existing import Undo is a separate action with its
own safeguards. Reconciled/linked records need defined dependency handling before
voiding. These are proposals, not permission to erase records or silently unlink.

## Test data and company selection

Migration preview QA and Receipt posting synthetic QA are developer test entities,
not client-facing workflow concepts. Separate synthetic testing from the normal
client workspace. Do not hide by name substring, silently delete/move reports or
rename companies to pretend QA data is genuine. Real reports currently live in a
QA-labelled company, so isolating fixtures must preserve those reports, IDs,
permissions, and provenance deliberately. Until separated, identify the local
QA environment and test-only entities explicitly; do not imply production data.
Company cards are unnecessary as the landing page's main content.

## Proposed delivery sequence (before continuing migration certification)

1. **UX-1 Workspace and browsing.** Consolidate navigation, one Upload entry point,
   separate Records table pages, company/source context and source-detail dialogs.
   Add backend cross-import queries, filter counts/totals and membership provenance;
   this is not just moving embedded tables. Keep prior URLs/history reachable.
2. **UX-2 Operational assignments and manual entries.** Bring forward the necessary
   Phase 3.4.2/4 foundation for bank classifications, descriptions, operation dates,
   expense periods, studio/method/terminal assignments, edit dialogs and explicit
   manual-create/void permissions. Keep future allocation/reconciliation bounded.
3. **UX-3 Pending work.** Unified source/assignment review entry, actionable table
   filters, clear out-of-scope vs invalid statuses, preserved work on reupload.
4. **UX-4 Client September rehearsal.** One-time migration into these same tables,
   second import/retry, overlapping routine sources and follow-up corrections.
   Prove totals and all manual work survive without duplicate movements or revenue.

Then continue full Phase 4 allocation/review, Phase 5 reconciliation, Phase 6 results
and dashboards, and Phase 7 pilot/release. Existing readers, deduplication, receipt
and invoice identities, audit and locks are reused. No rewrite of valid import
logic, production release or completed historical migration is claimed.

## Acceptance cases

- User can find all company records without opening any import batch and can
  filter the same rows by studio/month/missing assignment, with complete totals.
- Uploaded valid unclassified movements appear once; classify in a dialog later,
  reupload an overlapping report, and the assignment and row count survive.
- Native report preview shows actual range/source amount, original evidence and
  meaningful import outcome; source facts stay locked in ordinary Edit dialogs.
- A combined bank report populates debit and credit tabs without manual splitting.
- Pending source rows and out-of-scope purchases are accessible but not fabricated
  operational records, new revenue, or duplicate expenses.
- Invoice-level totals do not multiply by item/payment count; payment fractions
  remain distinct and company/currency totals are never combined incorrectly.
- One invoice table combines invoice/item and payment report information. Invoice
  dialogs handle zero, one and multiple payments with source facts locked and
  independently editable method/studio assignments; overrides survive reimports.
- Payment-before-invoice, link conflicts and cancelled invoices remain reachable
  in the secondary review view without fabricating invoice records or bank matches.
- Read-only users cannot create/edit/void; new action permissions are explicit;
  partial studio/sensitive access cannot leak rows, counts, origins or raw files.
- Source files, financial history and client reports remain intact when test data
  is separated; real-data migration/release remains explicit, not hidden QA cleanup.
