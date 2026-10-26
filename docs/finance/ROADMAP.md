# Finance development roadmap

Updated: 2026-10-25. Phase 0 accepted; Phase 1 implemented, validated, and accepted by the client. Phase 2.1 accepted; Phase 2.2 accepted; Phase 2.3 accepted (D-039); Phase 2.4 accepted (D-042); Phase 3.1 bank previews/history and initial 3.2 readers accepted (D-048); bank transaction commit/overlap/review/undo accepted (D-051). Phase 3.3.1 Alegra source previews accepted (D-056); Phase 3.3.2 sales posting/review/undo accepted (D-059); Phase 3.4.1 enriched source previews implemented; client acceptance pending. Financial migration and Phases 4–7 remain future work. See PHASE_1_DELIVERY.md, PHASE_2_1_DELIVERY.md and PHASE_2_2_DELIVERY.md and PHASE_2_3_DELIVERY.md and PHASE_2_4_DELIVERY.md and PHASE_3_1_DELIVERY.md and PHASE_3_2_DELIVERY.md for evidence.
Latest: Phase 3.3.3.2 shared receipt/routine import processing implemented; client acceptance pending.

Each phase begins with targeted business discovery and ends with validation,
documentation updates, and client acceptance. Acceptance is recorded in Progress.

| Phase | Subphases | Exit criteria |
| --- | --- | --- |
| 0 Specification | 0.1 Record source facts and accepted scope; 0.2 resolve business/ownership/access definitions; 0.3 sketch workflows and field dictionary; 0.4 establish reference calculations and acceptance cases | Client accepts specification; unresolved items have explicit dependencies |
| 1 Foundation and access | 1.1 Create finance app/feature flag; 1.2 establish company/account/currency foundations; 1.3 extend existing group/user capabilities and add group editor; 1.4 protected API/navigation and effective-access display | No finance access without grants; existing location limits and full-account isolation verified |
| 2 Configuration | 2.1 Accounts/terminals; 2.2 categories/subcategories; 2.3 payment/studio mappings; 2.4 dated fees/settlement rules and company tax profiles | Both countries can be configured through UI; Estepona mapping and inclusive-tax defaults work |
| 3 Imports and migration | 3.1 Raw history/preview; 3.2 bank readers; 3.3 Alegra invoice/items; 3.4 historical enriched-table migration; 3.5 overlap/conflict handling | Source totals match; migration retry and raw overlap preserve counts/manual work |
| 4 Review workflows | 4.1 Income assignments; 4.2 expenses/periods/manual splits and administration allocation by gross sales in expense month; 4.3 cash/transfers; 4.4 issue queues/bulk actions | Team can reproduce Excel review work with traceable corrections |
| 5 Reconciliation | 5.1 Validate Mindbody adapter; 5.2 daily/channel/studio comparison; 5.3 grouped/partial settlements and fees/reversals; 5.4 suggestions/manual resolution | Differences resolve through stored decisions without double matching |
| 6 Results and history | 6.1 Operating/final management calculations; 6.2 comparisons; 6.3 charts/drill-down/completeness; 6.4 auditable restatements and period groundwork | Reference results reproduce; changes visible; enforced closing deferred |
| 7 Pilot and release | 7.1 Staging/parallel Excel run; 7.2 access/regression verification; 7.3 client corrections; 7.4 controlled production/migration rollout | A real reporting cycle is accepted and release/recovery steps are documented |

## Phase discovery topics

- Phase 0: ownership, cash flow, fee policy, finance roles, shared expenses,
  transfers/financing/taxes, and the Spain sales report.
- Phase 1: group/user finance capability matrix, inherited/direct grants,
  sensitive categories and account/file visibility. Reuse existing location
  scopes; do not seed real user grants from assumptions or add parallel roles.
- Phase 2: actual terminals/accounts, taxonomy, category treatment, fee schedules,
  mappings, and active dates. Use configuration instead of hardcoded country lists.
- Phase 3: migration file scope/cutoff, enriched headers, supported formats,
  conflict resolution, retry/undo behavior, and invoice refresh semantics.
- Phase 4: review states, split allocation behavior, manual cash workflow, and
  bulk editing rules. Administration basis/month/zero-income fallback are
  confirmed; finalize refund, incomplete-income, rounding, and correction cases.
- Phase 5: settlement tolerances, timing, partials/refunds, source correction,
  and acceptable rules for automatic suggestions/confirmation.
- Phase 6: result calculation, actual-fee adjustment periods, completeness,
  historical corrections, and comparisons. Initial month locks are deferred.
- Phase 7: pilot operators, reference periods, staging access, migration sequence,
  deployment approval, and recovery procedure.

## Acceptance scenarios

| ID | Scenario and expected outcome |
| --- | --- |
| A-01 | Popular's two sections import as 175 movements: credits DOP 2,637,891.36 and debits DOP 2,491,914.56 |
| A-02 | Caixa imports 154 movements: credits EUR 45,351.16, debits EUR 41,260.92; supplied balances reconcile |
| A-03 | Alegra imports 438 invoices/456 items totaling DOP 2,574,587.60; repeated header totals do not inflate sales |
| A-04 | Three-item invoice B0100000317 totals DOP 13,280.00; repeated legitimate item names are preserved |
| A-05 | Repeat and reordered uploads retain counts; five same-looking Popular payments remain five movements |
| A-06 | Same-day same-amount TGSS movements remain separate; uncertain overlap enters review |
| A-07 | Migrate enriched workbook, retry migration, then import overlapping raw bank report: no double count and manual classifications survive |
| A-08 | Blank later fields do not erase manual values; conflicting explicit updates appear for review |
| A-09 | Unknown terminal and studio mismatch allow valid rows to import; General price list alone produces no studio mismatch |
| A-10 | Caixa ON 369092994 0610 maps to Estepona/October 6; month/year boundaries and invalid tokens behave explicitly |
| A-11 | Reviewed, classified, and reconciled states remain distinct; legacy checkbox alone creates no fabricated match |
| A-12 | Shared expense splits sum to the source amount; operation/payment dates and expense periods report independently |
| A-13 | Cash deposit/internal transfer does not create a duplicate sale; principal is separately displayed and excluded from profit, associated fees remain expenses; missing destination statement does not fabricate a bank counterpart or balance |
| A-14 | One deposit can settle many sales; partials, actual/estimated fees, reversals, and concurrent edits retain correct available amounts |
| A-15 | Studio user cannot retrieve other studios, full shared balances, unassigned records, source files, or leaked aggregate/export data |
| A-16 | Group/user grants combine by OR; UI explains inheritance. Removing a direct flag does not falsely imply an inherited permission is revoked. Removing all grants fails on the next backend request. Existing location limits remain enforced. |
| A-17 | Source/configuration updates preserve audit; currencies are never silently added. Initial v1 permits corrections without a mandatory close/reopen workflow. |
| A-18 | Existing operational imports, schedules, and analytics pass relevant regression checks |
| A-19 | Gross sale 10,000 less expected processing fee 350 compares to net deposit 9,650; fee is not subtracted again from the receipt. A distinct transfer fee of 100 remains separate. Monthly result is 9,550 before other expenses. If evidenced actual processing fee is 360, the fee effect becomes 360, not 350 + 360; adjustment is 10 under the defined period policy. Figures are illustrative, not observed rates. |
| A-20 | Group editor changes capability sets under existing user-management authority. Operational money/upload/edit flags alone do not grant finance access; ordinary Admin membership must not silently grant all new finance capabilities. Effective money and finance view gates, action gates, and account limits are tested separately. |
| A-21 | Shared administration of 12,000 for August, paid in September, uses August gross sales of 60,000/30,000/10,000: weights 60%/30%/10%, allocations 7,200/3,600/1,200. Company expense remains 12,000. Numbers are illustrative in one currency. |
| A-22 | Zero-income month leaves administration allocation pending with manual split available. Rounded allocations sum to the original cost; partial studio access does not change weights or expose restricted company data. |
| A-23 | V1 Spain sales of EUR 121 stay 121 in the management result, reconciliation base before fees, and administration income base. A recorded tax-bearing expense of EUR 60.50 stays 60.50; before other fees/expenses the result is 60.50. Tax defaults/source metadata are preserved, missing expense tax is not guessed, and no excluding-tax result is presented. Later default changes do not silently restate history. |
| A-24 | Manual expense displays manual origin; imported expense displays source filename/batch. Editing imported classification retains provenance; reimport and later manual/import overlap do not duplicate the movement. |
| A-25 | DR history starts January 2026. Spain expense-only periods before February 2026 remain flagged as lacking income coverage, not completed losses. No exact mid-2025 start month is invented. |
| A-26 | Caixa charge 36 and identified reimbursement 36 remain two bank rows, with net fee effect zero and no sales increase. Unknown AZUL charge remains for review. Amounts illustrative. |
| A-27 | Sale 100 in August refunded in September reduces August by 100; bank refund stays in September. Source cancellation plus refund cannot reduce income by 200. Missing sale link remains pending. |
| A-28 | Ordinary finance user sees authorized sensitive-category totals, not individual salary rows/identifiers or raw downloads; additional capability restores detail only within allowed scope. |
| A-29 | Operating result 1,000 plus extraordinary loan inflow 500 less equipment outflow 200 gives final management result 1,300. Employment contributions affect operating result; revenue-related tax payment affects extraordinary result. Source sales for Spain are Mindbody only in v1. |
| A-30 | Difference 0.01 DOP/EUR is a configurable rounding candidate, retained visibly and manually confirmed; 0.02 is outside the default threshold. No automatic write-off or source change. |

## Deferred tax reporting

Company tax defaults and preservation of explicit source tax values are v1 scope.
Expense IVA capture/recoverability and a consistent net-of-tax result are later
enhancements. They are not blockers for the accepted tax-inclusive v1 result.

## Deferred period closing and Spain source change

Initial v1 keeps period/history structure but has no mandatory close/reopen gate.
Enforced locks and their UI are later enhancements. Spain uses existing Mindbody
Sales initially; the future Alegra switch requires an explicit cutover and layout
validation, including consumer invoices without a client name. Neither future
feature is a blocker for Dominican foundation work.

These are planned tests, not completed validation. Create anonymized fixtures
before implementing automated tests. Add cases when discovery changes behavior.

## Definition of a delivered subphase

Record implemented behavior, affected files/migrations, relevant automated
results, manual acceptance steps, open issues, and client acceptance status.
Documentation-only tasks need document/link verification, not application tests.
Broaden runtime testing when changed dependencies or failures justify it.


## Added dependency: Phase 3.3.3 complementary Alegra payment import

D-065: inspect native payment export, then implement preview, receipt/allocation
posting and order-independent invoice linking before historical financial posting
(3.4.2) and channel reconciliation. Preserve already accepted invoice/bank import
behavior; extend partial-payment/status semantics deliberately. See
ALEGRA_DUAL_REPORT_IMPORT_PLAN.md for subphases and acceptance scenarios.
This dependency is planned, not delivered or tested.


Phase 3.3.3.1 workbook payment source previews implemented and validated;
client acceptance pending. Uses already-uploaded Alegra_adm sheets. Native payment
CSV contract, receipt identity/posting, invoice links and dependent undo are later
3.3.3 work before historical financial posting. See PHASE_3_3_3_1_DELIVERY.md.


Phase 3.3.3.1 payment preview accepted (D-066). D-067 confirms migration as normally
one-time setup; ongoing reports feed the same financial history. Next shared
payment/routine import discovery is PHASE_3_3_3_2_DISCOVERY.md (Q-016 pending).
Cross-entry deduplication and manual preservation take priority over additional
migration-only screens. No financial payment-posting delivery is claimed.


Phase 3.3.3.2 shared receipts, workbook handoff, strict CSV column preset, reviewed
commit/retain/assignment and protected undo implemented/validated; client acceptance
pending. Q-016 resolved (D-068). Native export acceptance, historical assignment/
provenance posting and completed September comparison remain dependencies; do not
claim this as a completed financial migration. See PHASE_3_3_3_2_DELIVERY.md.


## Future candidate: Alegra purchases and bank debits (D-070)

Client suggests linking native Alegra `Egreso` transactions (organizational purchases)
to bank debit movements in a later phase. Keep those entries outside the current
`Ingreso` customer-payment flow. Existing retained original reports/source cells
provide evidence for future discovery. Before implementation, define purchase
identity, payment/expense recognition, partial/combined settlements, refunds and
how to match existing imported bank expenses without counting an expense twice.
This is recorded future scope, not implemented matching or authorization to post
these purchases now. A later UI refinement should distinguish out-of-scope entries
from malformed source data; current previews label both as invalid source.


## Priority correction: daily workspace before migration certification (D-071)

Client requests a simpler Upload flow and all-records operational tables with
filters/edit dialogs. DAILY_WORKSPACE_PLAN.md defines proposed UX-1–UX-4 deliveries:
shared navigation/browsing, necessary Phase 3.4.2/4 assignment/manual-entry foundation,
pending-work filters, then September migration/routine-overlap rehearsal. This
reorders the next work around daily usability; reconciliation, results and release
remain later phases. Scope is documented, not a delivered table/editor or completed
migration. Q-017 confirms three Dominican uploads (combined bank, Alegra transactions, Alegra
invoices/items); Spain retains the existing Caixa/Mindbody source policy.


D-072 refines the pending UX delivery to three main record tabs: bank debits,
bank credits and invoices enriched by linked payments/items. Payment edits happen
inside the invoice dialog; unlinked payments remain reachable in secondary review.
Q-018 confirms source amounts/identifiers/client details remain read-only. No fourth
primary payment tab or manual source-fact editor is required for this workflow.


D-071/D-072 first UI delivery implemented; client acceptance pending. Records and
one Upload page, invoice/payment dialog, filters and audited receipt studio edits
reuse existing services. See DAILY_WORKSPACE_DELIVERY.md. Bank assignment/manual
entry/create-void services, unified pending work and fixture isolation remain before
full UX-2–4 / September certification; no full phase completion or release claimed.


2026-10-26: first daily workspace accepted. Bank assignment/edit foundation from
UX-2 /Phase3.4.2–4 is now implemented and validated; client acceptance pending. See
BANK_CLASSIFICATION_DELIVERY.md. Manual creation/cash, allocation, historical posting
and reconciliation are not delivered by this step. No full Phase4 completion claimed.


## Clean-replay checkpoint agreed 2026-10-26

Client accepts continuing iterative development/tests with current data and postponing
a reset until an appropriate checkpoint. Recommend a controlled clean replay AFTER
the first usable full path exists and has passed incremental client checks: routine
and historical imports, manual/cash classification, reconciliation and a monthly
management result. Perform this before certifying historical migration/production
rollout, so totals and classifications can be compared from a clean starting point.
An earlier disposable clean dataset can be used if a specific defect needs it; a full
reset is not required for ordinary UI tests or every delivery.

At that checkpoint, notify the client and prepare the exact recoverable replay plan:
- Preserve a database snapshot and all original reports; inventory affected imported
  and manual test records, review decisions, links and expected totals.
- Retain company/account/studio/terminal/category/source/fee configuration and access.
  Prefer a fresh isolated validation database/dataset over deleting the working set.
  Do not erase analytics/Mindbody data, users, configuration or stored originals.
- Define cutoff/authoritative report versions and baseline expected September results.
  Replay historical setup, routine reports, overlapping dates and both Alegra orders;
  check split payments, cancellations/refunds, manual overrides, terminal recognition,
  internal principal transfers, fees/reimbursements and operating/extraordinary totals.
- Compare counts, invoice/payment/bank totals, pending queues and monthly results to
  agreed Excel/source evidence before accepting migration. Keep the prior snapshot
  recoverable until sign-off. Do not silently convert this agreement into a purge of
  all companies or production data; exact scope is to be made concrete at checkpoint.

No reset is performed now. Flag this checkpoint during phase handoffs; it is not a
scheduled automation or a claim that reconciliation/results are already implemented.

2026-10-26 override (D-079): client requested the early reset immediately for an
August2026 test. Completed a recoverable reset of isolated local finance transactional
and preview data while retaining all configuration/access and other apps. Current
baseline is now empty, ready for client August uploads. The later full end-to-end
clean-replay checkpoint remains useful before certification; do not repeat a reset
without an explicit request. See BANK_CLASSIFICATION_DELIVERY.md for scope/backup.

2026-10-26 historical bank foundation: explicit selected workbook bank entries now
post through normal bank review/commit/undo while preserving mapped manual decisions.
All-date browsing, optional date filters and preview-company copy simplify the one-time
workflow. This advances the bank part of Phase3.4.2/3.4.3; it does not complete cash/
manual ledger, migration certification, reconciliation or results. Client real workbook
is still unposted pending company/account and bank-origin choices. See
HISTORICAL_BANK_POSTING_DELIVERY.md for tests, safeguards and replay steps.

2026-10-26 follow-up: the historical Alegra bank-to-invoice migration gap is addressed
with an explicit invoice-sheet adapter plus the existing payment importer, all dates
and split-payment preservation. Preview preparation and normal commit/review/undo are
available; client still needs to confirm real invoice/payment imports and validate
results. Bank recognition remains separate from reconciliation. This is additional
Phase3.4 foundation, not cash/manual ledger or full migration/reconciliation completion.
See HISTORICAL_ALEGRA_DELIVERY.md.
