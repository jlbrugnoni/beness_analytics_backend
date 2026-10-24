# Finance architecture

Status: accepted target design; Phase 1 accepted, Phase 2.1 implemented.
Updated: 2026-10-24. Implemented models are finance.Company, finance.Account,
finance.AccessChange, finance.Terminal, finance.ConfigurationChange and capability fields on existing access profiles. Financial
transactions, configuration beyond accounts/terminal mappings, and results below remain future work.
See PHASE_1_DELIVERY.md and PHASE_2_1_DELIVERY.md for exact endpoints and limitations.

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
  `GroupAccessProfileViewSet` under `can_manage_users`. The inspected frontend
  supports group assignment and user flags but has no group capability editor.
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
