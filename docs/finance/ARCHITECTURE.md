# Finance architecture

Status: accepted target design; Phase 1 accepted, Phases 2.1–2.4 accepted; Phase 3.1 accepted; Phase 3.2 accepted (D-051); Phase 3.3.1 source previews accepted (D-056); Phase 3.3.2 sales posting/review/undo accepted (D-059); Phase 3.4.1 migration previews implemented; client acceptance pending.
Updated: 2026-10-25. Implemented models are finance.Company, finance.Account,
finance.AccessChange, finance.Terminal, finance.Category, finance.SourceMapping, finance.ConfigurationChange, finance.FeePolicy, finance.SettlementPolicy, finance.TaxProfile, finance.BankImportBatch, finance.BankImportRow, finance.BankPosting, finance.BankMovement, finance.BankDecision, finance.BankEvent, finance.SalesImportBatch, finance.SalesImportRow, finance.SalesImportInvoice, finance.SalesPosting, finance.FinancialSale, finance.SalesDecision, finance.SalesEvent and capability fields on existing access profiles.
Sales posting is implemented; broader expense classification, bank reconciliation and results remain future work.
See PHASE_1_DELIVERY.md, PHASE_2_1_DELIVERY.md and PHASE_2_2_DELIVERY.md and PHASE_2_3_DELIVERY.md and PHASE_2_4_DELIVERY.md and PHASE_3_1_DELIVERY.md and PHASE_3_2_DELIVERY.md for exact endpoints and limitations.

Current shared receipt/import checkpoint: Phase 3.3.3.2 implemented; acceptance pending. See PHASE_3_3_3_2_DELIVERY.md.

## Existing integration points

- `core_data.models` owns users, `Site`, `Studio`, `PaymentMethod`, `SaleLine`,
  source rows, and import history. `Site` identifies country and Mindbody context;
  it must not automatically be treated as a legal company or bank account owner.
- `core_data.access` combines group/user capabilities and operational site/studio
  scopes. Existing `Admin` membership currently grants global access. A finance
  capability evaluator must not accidentally turn Admin membership into all
  finance actions. Keep existing operational access behavior intact.
- `GroupAccessProfile` and `UserAccessProfile` already store the same six
  operational capability flags. Group profile CRUD is exposed through
  `GroupAccessProfileViewSet` under `can_manage_users`. At initial inspection the frontend
  supported group assignment/user flags without a group capability editor;
  Phase 1 subsequently implemented that editor.
- `core_data.permissions.CapabilityPermission` and frontend `useAccess`/
  `routePermissions` provide existing integration patterns, not sufficient
  financial authorization by themselves.
- `SaleLine` contains sale date/number, method, studio, items, and paid amounts.
  Validate export semantics before choosing Spain's collection aggregates.

## Boundaries

Create `finance` in the existing Django project and a dedicated `/api/finance/`
namespace. Use the same database and authentication. Refer to existing studios
and users; own financial records and policy in the new app.

Keep API/serialization, access decisions, import readers, domain operations,
report queries, and tests in distinct modules. Source readers translate formats;
they must not each invent financial identity, permission, or classification rules.
Choose actual filenames as implementation grows rather than precreating empty
layers. Keep business policy out of frontend-only calculations.

Proposed dependency direction:

`existing users and studios -> finance records/configuration -> finance services -> API -> frontend`

V1 reads existing Mindbody Sales for Spain through a source-linked adapter;
DR imports Alegra. A company/period has one authoritative sales source. Do not
create a second routine Spain upload or sum a source and its projection. Spain
Alegra is a future option, including consumer invoices without client names.
Source corrections require auditable refresh/review of affected results;
enforced period closing is deferred.

## Proposed record groups

| Group | Responsibility |
| --- | --- |
| Company and accounts | Legal ownership, country, currency, bank/cash account, participating studios |
| Configuration | Terminals, channels, source mappings, categories/subcategories, dated settlement/fee rules and company tax profiles |
| Import batch and raw rows | File metadata, source/account context, preview/commit result, row provenance, issues |
| Bank/manual movements | Original financial movement, direction, amount, balance, source and current interpretation |
| Sales and items | Alegra invoice header/items or source-linked Mindbody sales view; total counted once |
| Allocations | Expense period/category/studio splits without duplicating the movement |
| Reconciliation | Settlement groups, allocated sales/receipt amounts, fees, differences, decisions |
| History and period control | Actor/time, original/current values, source changes, closing/reopening |
| Access profiles | Extend existing group/user capabilities; reuse allowed sites/studios and enforce account visibility |

Company baseline: Beness Pilates Studio S.R.L. for the Dominican reports and
Bewellness Group SL for the Spain Caixa account. Keep an operating account, a
savings account, and studio cash as separate configurable accounts when present;
initial DR setup and terminal mappings are recorded in INITIAL_CONFIGURATION.md.

Use decimal amounts and explicit currencies. Validate that allocation sums and
reconciliation amounts do not exceed available values. Preserve partial/unassigned
amounts. Match/resolve operations require atomic writes, concurrency protection,
and stale-data checks. Corrections must be reversible through recorded actions.

## Provenance and special movements

Retain creation origin separately from manual edits. An imported record retains
its source filename/batch when edited. Later imported counterparts of manual
bank entries need linking/review, not duplication. Manual cash entries do not
prove a verified cash balance. Migration preserves existing assignments and marks
its own provenance rather than claiming the record was typed in the app.

Refunds link to original sales, with original result period and actual bank date
and channel separate. Avoid applying source cancellations and refund adjustments
twice. Missing linkage stays pending. Recompute affected original-period results
and allocation inputs with history; negative bases need explicit handling.

Preserve Caixa fee debits and reimbursement credits. A reviewed reimbursement
offsets the identified fee without inflating sales or deleting source rows.
Offer eligibility dates are configurable; unknown AZUL debits stay for review.

Management formula: operating plus extraordinary inflows less extraordinary
outflows. Loan receipts affect final management figure only. Revenue-related
tax payments are non-operating; employment contributions are operating. Map
exact categories independently of direction and sensitivity. Do not label the
custom tax-inclusive management measure EBITDA.

Configurable rounding-review threshold defaults to 0.01 DOP/EUR. Within-threshold
differences remain explicit review candidates, not automatic matches/write-offs.
Never use tolerance to deduplicate movements or hide invoice-total failures.

## Configurable tax profiles

Company defaults describe rate/treatment, price inclusion, and effective dates.
Initial client-provided setup: Bewellness Group SL has 21% IVA included in sales;
Dominican activity has no sales tax. Keep taxable/exempt/no-tax/unknown distinct.
Prefer explicit source tax amounts/treatment; configuration supplies missing
information under a recorded rule and must not silently overwrite the source.
Future default changes do not silently restate imported or closed periods.

V1 retains original totals and any explicit source tax values/rule provenance;
missing tax details remain unknown. Full expense-tax capture and a net-of-tax
result are deferred (D-016). Do not implement an excluding-IVA result just because
the tax rate is configured. When future extraction is required for a single known
inclusive rate, base = total / (1 + rate), tax = total - base; multiple rates and
item/invoice rounding must then be validated.

Bank reconciliation uses the original customer-paid total and the applicable
processing-fee base, not automatically the excluding-tax amount. V1 monthly
results retain IVA in sales and recorded full expense totals; administration
weights use tax-inclusive gross sales before fees. Expense tax is separate:
a bank debit alone does not prove its VAT rate
or recoverability. Preserve unknowns rather than assuming every expense has 21%
or has no tax. Statutory tax filing remains outside the initial module scope.

## Administration allocation

Confirmed inputs (D-013/D-014/D-016): gross sales including IVA before processing fees for the expense
month, allocated across the eligible studios of the company. Account and report
currency remain explicit; never combine DOP and EUR in one allocation base.
Define studio/company membership and incomplete or unmapped sales before
finalizing any allocation, rather than silently omitting missing source data.

Retain a company-wide source expense and separate studio allocations. Distinguish
shared treatment from expense category and any direct historical assignment.
Store the applied period, basis, studio gross-sales amounts, weights, source
version, resulting amounts, and any manual override. A zero-income month stays
pending with a manual split available; do not default to equal shares.

Company totals include the parent cost once. Studio results show direct expense
and allocated administration. Restricted studio access filters presentation,
not the denominator used to calculate allocations. Do not recompute shares using
only the studios visible to the current user, or expose restricted company base
amounts through the studio explanation. Permission rules still apply to source
documents and company-wide payroll detail.

Use deterministic currency rounding with a recorded remainder assignment so
studio amounts sum exactly to the expense. Handle source changes through an
auditable recalculation/confirmation and closed-period policy; never silently
change a finalized month. Refund/non-positive-income edge cases remain for
allocation-stage discovery.

## Internal movements and fee components

Internal movement is a transaction kind independent of expense category. This
allows transfer linking, account balances, and report treatment to share one
definition instead of depending on a free-text category. Preserve both imported
legs when both accounts are available. A single imported leg must remain useful
with a destination account and an unmatched-counterpart state; do not fabricate
a bank movement or a verified destination balance. Cross-company/owner transfers
require their own policy, not automatic own-company transfer classification.

Support cash-to-bank and operating-to-savings movements. Link a later counterpart
without double counting. A studio user's access must not expose the other
account's restricted statement. Profit exclusion/separate display is accepted
in P-001. Keep these movements visible even if the savings account's statement
has not been imported.

For reconciliation, distinguish gross sale amount, expected withheld fee, expected
net settlement, actual bank receipt, and any unresolved difference. Keep a
separately charged bank fee distinct from withholding. Observing a net deposit
does not alone prove the fee: the difference may also include refunds, missing
sales, timing, or other adjustments. Actual fee evidence can come from settlement
details or an explicit reviewed assignment. Monthly results use estimated fees
with actual adjustments when available (P-002). Retain estimate and actual
provenance but use the applicable amount once; log the difference as an adjustment
under the period policy still to be defined. Never deduct the same processing
fee from both gross sales and the already net bank receipt.

## Import contract

1. Identify the source layout and validate company/account/currency context.
2. Preserve raw rows and parse dates/numbers without changing their meaning.
3. Build identities from source facts independently of manual classifications.
4. Produce a preview of new, unchanged, changed, invalid, and ambiguous rows.
5. Revalidate preview/source versions when committing. Do not silently apply a
   stale preview over another user's changes.
6. Commit valid independent rows and durable review issues; report both counts.
7. Retain provenance across migration, routine imports, repeated uploads, and
   rule changes. Source-file hashes alone cannot identify overlapping transactions.

Absence from a partial-period upload is not deletion. An invoice has no exported
item ID in the sample, so preserve repeated item occurrences and define safe
invoice refresh semantics before allowing automatic item replacement.

## Access design

The client chose continuity with the current group/user system (D-012), leaving
the implementation choice to the developer. Use editable group capability sets
plus additive user grants. Do not create a parallel finance-role assignment
system for v1. Reuse existing allowed-site/studio location limits.

Effective capability is the OR of grants from all groups and the user profile.
Show inherited versus direct grants in the UI. Removing a direct grant does not
remove an inherited grant; the user must leave/change the granting group to lose
it. V1 does not support explicit deny flags or a different capability set per
studio. Document this limitation instead of implying granular scoped roles exist.

Candidate finance capabilities, to implement and name consistently in Phase 1:

| Capability | Purpose |
| --- | --- |
| `can_view_finance` | Enter finance and view permitted financial records/results |
| `can_import_finance` | Preview/commit financial and migration uploads |
| `can_edit_finance` | Classify movements and edit permitted business assignments |
| `can_reconcile_finance` | Resolve and undo permitted collection matches |
| `can_manage_finance_settings` | Maintain accounts, terminals, categories, mappings, and rules |
| `can_close_finance_periods` | Close/reopen financial periods with audit |
| `can_export_finance` | Export permitted financial records |
| `can_view_finance_bank_accounts` | View full statements/balances/source files when account scope permits |
| `can_view_sensitive_finance` | View sensitive category item and identity details within scope |

Finance data access requires effective `can_view_money` and `can_view_finance`;
each mutation/export adds its own capability and relevant scope check. Imports
show financial data, so their previews also require financial viewing. Group
capability editing uses existing `can_manage_users` authority and existing
administrative assignment protections. Display prerequisites instead of treating
`can_edit_data` or `can_upload_data` as financial authorization.

Add a group capability editor and effective-access explanation to user management.
Changes to existing operational group flags affect existing users too; show that
effect clearly and audit group changes. Preserve established defaults and add no
finance grants to ordinary existing groups/users silently.

The current `user_has_capability` globally allows existing Admin users; do not
simply append finance flags to that list and unintentionally grant all of them.
Separate financial capability evaluation from the operational Admin shortcut.
Retain Django superuser full technical administration; ordinary Admin group alone
does not grant new finance capabilities. Test both behaviors explicitly.

Separate full bank-account/source-file access from studio result/record access.
Shared account balances, unassigned records, company expenses, previews, and
downloads need explicit broader grants. Validate scope for linked objects and
write targets, not only filtered list queries. Reusing a site filter does not
grant visibility of another site's account or a shared full statement from a
partial studio scope. Without the sensitive-detail capability, category totals
remain visible in permitted results but individual sensitive payments, names,
descriptions, and identifying details are restricted across API/search/history/
reconciliation/export paths. Parent category sensitivity is inherited. Raw files
containing sensitive records require the capability; provide sanitized exports
otherwise. Sensitivity never grants broader location or action access.

Extend the existing access payload and frontend navigation without changing the
meaning of operational capabilities. Backend authorization is authoritative;
permission revocation must take effect on subsequent API requests even if the
frontend has an old cached access payload.

## Release design

Use corresponding phase branches, additive migrations, a finance feature flag,
and staging validation. Apply migrations and runtime releases in a documented
compatible order. Feature disabling is distinct from reversing migrations or
deleting imported financial data. Write the concrete deployment, backup, and
recovery steps before the first online pilot. Preserve period references and
history, but defer enforced closing/reopening and close UI for initial v1 use.

Keep currencies separate in v1. Automated exchange-rate consolidation, bank APIs,
tax filing, and forecasting are outside the initial scope.

## Implemented category configuration (Phase 2.2)

Company-owned root categories and one child level are live. The empty-catalog
initializer uses a common approved baseline with explicit stable codes, while
names, flags and defaults stay independent per company. Custom later categories
receive independent identifiers; later cross-company alignment/copying is separate
from this baseline. Details and limitations are in PHASE_2_2_DELIVERY.md.

Own sensitivity combines with parent sensitivity by OR. Active state combines
with the parent's by AND. Child defaults can inherit parent treatment/allocation.
Company-wide settings scope controls writes; sensitive-detail capability also
protects sensitive categories, changing sensitivity and editing a parent with
sensitive children. No sensitive transaction endpoint exists yet. No result or
allocation calculation is performed by editing category defaults.

## Implemented source interpretation (Phase 2.3)

SourceMapping stores company/source-field/normalized-value identity and an explicit
studio/channel, review or neutral result. Source identities are immutable; targets,
review and active flags are audited editable settings. Interpretation retains raw
labels and rule/version evidence; manual choices take precedence with source
warnings retained. The API test area invokes the helper without importing or
saving financial corrections. Actual adapters/import persistence remain later work.

Alegra cost center is primary and price list is secondary warning evidence;
General is intrinsically neutral. No price-list fallback or fuzzy alias matching.
Client DR conventions and the mixed credit/recurring review case are recorded in
BR-045. Spanish Mindbody alias names remain unguessed (BR-046).

## Implemented dated policies (Phase 2.4)

FeePolicy, SettlementPolicy and TaxProfile share nullable baseline/start/end,
notes, active state and revision. Inclusive intervals may not overlap active
rules of the same type/company/channel (tax has no channel). API writes lock
Company first, including setup; model validation checks overlap under that lock.
Do not bypass this path with unvalidated ORM writes. Technical admin is read-only.
Company/channel cannot be reassigned. Company site is protected by any policy;
company currency is also protected by fee policies with monetary fields.

The preview helper resolves policy IDs/revisions by operation date. It computes
withheld percentage from gross, rounds that fee once to 0.01 using ROUND_HALF_UP,
then subtracts the rounded fee. Full-deposit policies preserve the gross amount;
independent charges are returned as metadata, not deducted again. Included sales
tax is informational; result_basis stays tax_inclusive. Unknown tax/withholding
remains null/review. Explicit source-tax precedence belongs to the later adapter.
No invoice/payout rounding policy is asserted by this isolated preview.

Settlement output is elapsed-hour metadata and a weekend-delay flag; it computes
no bank due date and uses no holiday calendar. Reimbursement fields describe
expected offers, not matched refunds or automatic accounting entries. Current
policies are company/channel scoped; provider/account-specific overrides are not
implemented. Exact future actual-fee adjustment periods remain Phase 5/6 work.

## Implemented bank preview foundation (Phase 3.1)

BankImportBatch owns immutable original bytes, account/provider context, hash,
encoding/parser version, actor/time, summary/issues and earlier-identical-batch
reference. BankImportRow preserves every CSV record and physical source line
range, including headers/preamble/blanks, parsed values and issue codes. Unique
(batch,row_number) identifies a source occurrence, not a financial movement.
There is deliberately no globally unique bank transaction hash or financial
movement model in this delivery. Existing core_data operational imports are intact.

Raw source storage is bounded database BinaryField, never a media URL. No raw
preview models are registered in admin. All history/detail/row/original surfaces
require finance view/money plus full-account and sensitive-detail capability.
Create/original retrieval also require import capability. Rows inherit account
scope through the parent batch; recheck state/scope before atomic persistence.
Responses are private/no-store. Raw strings are rendered as text, not evaluated.

Explicit provider/currency/country checks and versioned readers preserve money
as decimal strings, dates as ISO values, and original cells separately. A failed
file may retain a parsed prefix, but its status remains failed and no commit is
possible. Missing/invalid source values never generate movements. Observed date
ranges do not establish report completeness. Bank account numbers in preamble
are preserved but not automatically matched to configured account ownership.

Preview retries append upload history; only identical bytes under the same
account/provider link to an earlier batch. Different-file overlap matching and
financial undo remain next steps. A-01/other financial import scenarios are not
considered implemented merely by passing reader controls.

## Implemented bank financial posting (Phase 3.2)

Raw batches keep their original parse status/summary. BankPosting is a separate
one-to-one execution with actor/state/revision. BankDecision records each source
occurrence's outcome/resolution and optional movement link; (posting,movement)
is unique when assigned so repeated source occurrences cannot collapse together.
BankMovement owns current bank source data, indexed non-unique fingerprint,
creation row, active/reconciled flags and revision. BankEvent retains actor/time,
reason and before/after snapshots. No financial model is registered for unaudited
admin writes. Classification and sales records are separate future domain work.

Account.ledger_revision is independent of configuration revision. Processing
plans use a deterministic version token; all supported financial writes acquire
Company then Account locks and advance the ledger revision. Review checks the
plan, decision and target versions. Repeated same-batch commit is idempotent;
undo requires a new source preview before that batch can post again. Account
kind cannot change to cash once bank preview history exists.

Automatic exact identity resolution is occurrence-aware and evidence-based, not
a unique global hash. Same-file source links survive retries; changed current
movement values trigger review rather than automatic reversion. Different-file
repeated groups remain ambiguous. Missing identity evidence means detection has
limits; never claim every amount/date change can be identified automatically.
References, date/description and reported balance propose candidates only.
Manual resolution requires a reason; bank correction preserves old source values
in audit and changes no classification fields. Reconciled records cannot be
corrected here. All targets are active, same-account and same-provider.

Undo ownership is financial committer, not raw uploader. Import/edit capability
is mandatory; settings capability additionally permits others' postings. Reused
records are not reversed. Created records must be active/revision 1, unreconciled
and unsupported by other active/partial-undo postings. Approved source corrections
are protected. Undo marks eligible movements inactive, keeps audit/raw evidence,
freezes pending decisions and records the request token/result for replay safety.
Fresh previews can complete a partial undo after independent dependencies clear;
no manager force path bypasses protection. Future financial edit/match APIs must
use these locks and advance both relevant revisions, not mutate ORM rows directly.

Bank batch APIs expose processing_status separately from parse status. Movement
history exposes source batch IDs for consistent tracing. Ledger/candidates/events
inherit full bank and sensitive-detail gates from 3.1. No result engine, verified
balance, bank-number ownership detection or sales reconciliation is implemented.

## Implemented sales source previews (Phase 3.3.1)

SalesImportBatch/Row/Invoice store immutable Alegra source evidence, not financial
sales. Group by full invoice code within one company/provider/batch, preserving
item multiplicity and validating header consistency plus exported item-total sum.
SUBTOTAL - PRODUCTOS/SERVICIOS varies per item in the sample. Repeated tax headers
remain raw positional evidence. Unknown status is review-only; only Cobrada counts
in validated paid preview totals until further status evidence is confirmed.

Sources require company-wide site access and sensitive detail; partial studio
access cannot expose them. Upload/original retrieval also require import. There
is no global cross-batch sales identity/posting/cancellation engine yet. Future
posting must honor immutable invoice facts, explicit status approval, manual
assignments and original-period refunds without double deductions.

## Implemented sales financial posting (Phase 3.3.2)

FinancialSale holds the original source/item snapshot and separate studio/channel/
cancellation assignments. Only active company/provider/code is unique. SalesPosting
owns decisions for one immutable source batch; SalesEvent preserves before/after
history. Source rows and historical v1 summaries are never rewritten. Parser v2
recognizes confirmed Anulada; posting interpretation v1 recognizes it from old
stored previews while recording its version in audit.

Compare invoice facts plus item evidence as a multiset. Unknown/incomplete source
invoices do not post; independent valid invoices continue. Unexpected changed facts
are anomalies, not editable source fields. A later cancellation requires approval;
old paid evidence never restores status automatically. Cancelled sales contribute
zero in the original invoice period. No bank debit or automatic refund deduction
is created. Settlement treatment/replacement is operator evidence for Phase 5.

All financial writers lock Company and advance sales_revision. Plan tokens include
ledger/company/rule revisions; individual edits/decisions require current revisions.
PostgreSQL assignment locking uses FOR UPDATE OF self to avoid nullable-studio
outer-join locks. Undo only reverses eligible untouched creations; edits, linked
replacement targets, reconciliation, other imports and approved cancellations are
protected. All source/ledger/history paths retain full company/privacy gates.

## Implemented enriched source previews (Phase 3.4.1)

MigrationImportBatch/Row retain the native DR workbook, selected pilot month,
raw cells/formulas/caches, known sheet/column map, dates/amounts and legacy manual
fields. Standard-library ZIP/XML reader has bounded archive/part/row/cell limits,
rejects DTD/macros/invalid references and never executes formulas or external links.
Only Debitos/Ingresos create preview rows; summaries/Alegra sheets remain original
comparison evidence. Generic column-mapping controls remain a later extension.

Payment origin is explicitly unknown; no bank/cash account or verified balance is
inferred. Checkbox-only rows are ignored, nonempty incomplete data remains review
evidence, cached errors leave values unresolved and valid independent values stay
visible. Distinct bank/operation/expense dates govern separate totals. Source
preview never creates financial movements, sales, assignments or reconciliation.
All source paths require site-wide company finance/money/bank/sensitive access;
upload/original retrieval also require import. Existing bank/sales ledgers remain
unchanged. Source coverage is measured from saved data, not client-stated cutoff.


## Planned complementary Alegra payment source (D-065)

Original invoice/items remain the authoritative sale; native payment export adds
separate receipt/allocation evidence and does not add revenue or bank transactions.
Mixed-method historical receipts require support. Invoice → payment → bank is the
recommended operator sequence, but safe pending links must allow any arrival order.
Current code has invoice and bank posting only; native payment import/allocation
is not implemented. See ALEGRA_DUAL_REPORT_IMPORT_PLAN.md for identity, source
conflicts, privacy, completeness, dependency/undo and discovery requirements.


## Implemented workbook payment preview — Phase 3.3.3.1

GET migration-imports/{id}/payments/ derives bounded, versioned Alegra_adm evidence
from immutable workbook bytes without new DB rows. Separate raw payment number,
original associations, original/corrected methods and prior flags remain intact.
Exact source-reference grouping is not a posted invoice link. Company-wide source
privacy reuses migration controls; source cells are paginated with payment rows.
See PHASE_3_3_3_1_DELIVERY.md. Financial receipts/allocations, cross-file duplicate
decisions, posting/linking and undo remain planned; preview does not alter the
single source channel on existing FinancialSale records.


## Migration versus routine operation (D-067)

Historical migration is normally a one-time setup entry point; recurring bank,
invoice and payment report uploads maintain the same financial records. Both
adapters must share identities, assignments, matching/review and dependent-undo
services. Never fork financial history by entry point or require a recurring
manual workbook. See PHASE_3_3_3_2_DISCOVERY.md for the receipt structure and
cross-entry overlap acceptance cases. Payment financial posting remains planned.


## Implemented shared receipts and routine payment imports — Phase 3.3.3.2

PaymentImportBatch/Row → PaymentPosting/Decision/Event → FinancialReceipt is the
shared path for initial workbook payment preparation and routine CSV previews.
Original sources/assignments remain distinct; active company/provider/number
identity is verified against source facts. Receipt.sale is a single-invoice
allocation for the full receipt amount in v1. Several receipts can link one sale;
multiple-invoice rows remain unsupported/reviewed. Company locks and payment/sales/
mapping revisions guard commit and linking; linked active receipts protect sale
undo. Payments do not add revenue or bank movements. See
PHASE_3_3_3_2_DELIVERY.md for implemented behavior and outstanding native-format,
missing identity, source-replacement and historical migration limitations.


Routine payment input correction D-069: original XLSX is supported through
alegra-payment-xlsx-v1 using name-independent table/header detection. Historical
preview remains strict to the known Alegra_adm worksheet; neither mode rewrites
original evidence. Both feed the same receipts. See PAYMENT_XLSX_CORRECTION.md.
