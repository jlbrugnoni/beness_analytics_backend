# Finance business rules

Updated: 2026-10-24. Status: accepted baseline with discovery still open.

The accepted rules below come from client instructions and the supplied reports.
Items explicitly marked pending require a business answer or source validation.

## Scope and ownership

- **BR-001:** Build a dedicated Django `finance` app. Reuse existing users and
  studios. Support Dominican Republic and Spain through one financial structure
  and source-specific import mappings.
- **BR-002:** Terminals, accounts, categories, subcategories, source mappings, and
  settlement/fee rules are editable configuration. Used configuration retains
  historical references and can be deactivated. Historical calculations must not
  change silently when current configuration changes.
- **BR-003:** Keep company ownership, country, currency, account, and studio
  distinct. Dominican report owner is Beness Pilates Studio S.R.L.; the client
  identified Spain's Caixa owner as Bewellness Group SL. DOP and EUR results
  remain separate initially. Configure Dominican Republic first. Recommended
  initial editable label: `Banco Popular - Cuenta operativa (DOP)`, for Beness
  Pilates Studio S.R.L.; this is a label proposal, not a created account. Savings
  and other accounts remain configurable; do not invent identifiers or balances.

## Sales and studios

- **BR-004:** In normal Dominican operations, an Alegra invoice is created when
  the client pays. Default its payment date to its invoice date, with a recorded
  correction available for exceptions.
- **BR-005:** Import the item-level Alegra report once. Group items under the
  invoice code within its company/source. Store the invoice total once. Preserve
  repeated legitimate item occurrences and verify item totals against the
  exported invoice total. A future tax-bearing export needs explicit validation.
- **BR-006:** Use mapped `Centro de costo` as the primary Alegra studio value.
  Flag a conflicting studio-specific price list. `General` is neutral evidence.
  Missing/unrecognized cost centers enter review. A warning does not prevent
  valid records from importing.
- **BR-007:** Preserve Alegra's original payment method separately from the
  operational channel: terminal/Cierre, link, recurring, transfer, cash, or other.
  Support manual corrections now and mappings for future Alegra method names.
- **BR-008:** Spain currently uses the Mindbody Sales report for better date
  precision. The client's target is Alegra for both countries after improving
  Spain invoice registration. Confirmed v1 sources: Alegra for DR, existing
  Mindbody Sales for Spain. Support explicit authoritative source by company/
  period; do not sum overlapping sources. No Spain cutover date is assumed.
  Later Alegra support needs Spain layout/timing validation. Its consumer invoices
  may lack client names; do not reject them or invent identities when supported.
  Invoice identity is company/source/code, not name.

## Bank movements and reconciliation

- **BR-009:** Preserve original source values and provenance separately from
  assigned operation date, studio, channel, category, and review decisions.
- **BR-010:** Banco Popular has credit and debit sections with repeated headers.
  Amounts are positive; bank transaction type determines direction. References
  and serial numbers are optional and may repeat across legitimate movements.
- **BR-011:** Caixa has one newest-first list with signed EUR amounts and no
  separate account or transaction identifier. Select its configured account at
  upload. Parse the file's actual numeric/date format explicitly.
- **BR-012:** Client-confirmed Caixa terminal `369092994` belongs to Estepona.
  In `ON 369092994 0610`, `0610` means operation date October 6. Resolve the year
  relative to the bank date, including year boundaries; surface invalid or
  ambiguous dates rather than forcing a fixed one-day subtraction.
- **BR-013:** Compare sales and collections by operation/payment date, studio,
  and assigned channel. Support many sales per deposit, partial settlements,
  fees, reversals, and saved manual resolutions. Matching suggestions do not
  constitute a confirmed match.
- **BR-014:** A positive bank movement is not automatically sales income. Cash
  deposits, internal transfers, refunds of bank charges, and financing movements
  require an explicit treatment. The client requested an internal-movement type
  for cash deposits and transfers between own operating/savings accounts. Cash
  sales should already exist in Alegra/Mindbody; confirm coverage instead of
  inventing sales when a cash deposit is found. Show internal movements in a
  separate section and exclude own-company transferred principal from income,
  expenses, and profit; associated bank fees remain expenses. Cash expenses can
  be entered manually under BR-035. Verified cash balances/opening balances are
  not assumed from the current reply.
- **BR-015:** Preserve legitimate repeated payments. Mutable classifications and
  source row positions are not permanent identities. Use source facts, account,
  balance/context, and occurrence handling; ambiguous overlaps enter review.
- **BR-016:** Separate financial review status, classification completeness, and
  reconciliation status. Completing one does not automatically complete another.

## Expenses and monthly results

- **BR-017:** Store payment date and expense period separately. Monthly expense
  reporting uses the assigned expense period; bank movement reporting uses the
  bank date. Missing periods remain visible as unresolved records.
- **BR-018:** Expenses support description, category/subcategory, studio, review
  status, and manual splits. Shared expense allocations must reconcile to the
  movement without duplicating it. Company-wide expenses classified as
  administration are allocated by income share under BR-032.
- **BR-019:** Show bank movements, reconciliation, and monthly management results
  as distinct views. Income comes from the designated sales/payment source;
  bank differences remain visible. AZUL deposits are already net of processing
  fees. Reconciliation compares gross Alegra receipts less the configured
  channel-specific fee against that net deposit; do not subtract the fee again
  from the bank amount. Separately charged transfer/bank fees remain distinct.
  Use configured estimated processing fees in monthly results and adjust them
  when actual fee evidence becomes available. Count the underlying processing
  fee once, replacing/adjusting the estimate rather than adding the full actual
  amount on top. Unidentified separate AZUL debits still need classification.
  Tax defaults are configurable under BR-033. V1 uses tax-inclusive sales and
  recorded expense totals under BR-034; expense tax separation is deferred.
- **BR-020:** The client classifies financing, large equipment purchases, and
  tax payments as non-operating/extraordinary and wants operating and final
  monthly results separately. Final management result = operating result +
  extraordinary inflows - extraordinary outflows. A loan receipt increases that
  final figure but stays outside operating result. Taxes the client describes as
  revenue-related are non-operating; employment taxes/contributions are operating
  costs. Individual tax categories are mapped during setup; unidentified bank
  transaction taxes are not silently inferred from these two classes. Preserve
  bank direction. Use management-result labels; the current custom classification
  and tax-inclusive basis do not establish a defined EBITDA measure. Formal
  EBITDA/net-tax reporting is a separately defined future calculation.
- **BR-021:** Results expose outstanding classification and reconciliation work.
  A month with incomplete source coverage must not be presented as complete.
  Enforced closing/reopening is deferred for initial use. Keep history and period
  references ready for later controls; do not block v1 edits on a closing process
  the client is not yet adopting. Corrections remain auditable.
- **BR-032:** Keep company-wide administration expenses as original company
  costs and allocate them to studios in proportion to gross sales before
  processing fees, including IVA where charged in v1. Use sales from the expense's assigned month, not payment month:
  studio weight = studio gross sales / total eligible studio gross sales;
  allocated expense = shared cost × weight. Preserve category and original cost.
  Show direct expenses, allocated administration, and the resulting studio result
  separately. Company results count the shared expense once, not both the parent
  and allocations. If the allocation month has no income, leave it pending with
  a manual split available. Shared administration is an explicit allocation
  treatment; category name alone must not override a historical studio assignment.
  Refund/non-positive-income edge cases and later source corrections require
  detailed validation before allocation implementation (Q-005).
- **BR-033:** Configure sales tax by company with effective dates and whether
  source prices include tax. Client-provided starting setup: Bewellness Group SL
  sales include 21% IVA; the Dominican activity has no sales tax. These are client
  business inputs, not a verified statement of tax law or a blanket rule for
  every transaction in either country. Preserve explicit source tax details and
  allow reviewed exceptions; do not hardcode country-wide rates. Preserve original
  totals and any explicit source tax details separately. Missing tax breakdowns
  remain unknown; complete tax calculations are not a v1 acceptance requirement. Bank
  reconciliation retains the full customer-paid amount. Taxable, exempt/no-tax,
  and unknown status must be distinguishable. Expense tax must not be inferred
  from the company's default sales rate. See BR-034 for the accepted v1 result
  basis and the deferred net-of-tax comparison.
- **BR-034:** V1 monthly management results retain IVA in Spain's sales and use
  expense totals as recorded, including tax where present. Do not remove IVA
  from sales while leaving expense totals inclusive. Administration allocation
  uses that same tax-inclusive sales base before processing fees. Label this
  result's basis explicitly. A later version may capture expense tax/treatment
  and provide a net-of-tax comparison once both sides can be represented
  consistently. Configurable sales-tax metadata remains in v1; statutory tax
  calculations and recoverability decisions are not implied by it.
- **BR-038:** Customer refunds reduce sales/results in the original sale month.
  Preserve the original sale and record its linked refund/cancellation adjustment;
  retain actual bank refund date and channel separately. Missing original-sale
  linkage requires review, not a guessed month. Avoid applying both source
  cancellation and a refund adjustment as two reductions of the same sale.
  Recompute affected original-period results and allocation inputs with history.
  Late refunds require controlled restatement when closing is introduced later.
- **BR-039:** Caixa's introductory terminal offer charges a fee and then credits
  its reimbursement as a separate bank movement during the first year. Preserve
  both legs. A reviewed fee reimbursement offsets the relevant fee expense; it
  is not customer sales or an own-account transfer. Do not assume every positive
  T.PlanaMyCommerce row or later fee is covered; retain eligibility dates/mapping
  and review unmatched reimbursements. Unidentified AZUL debits remain for review.
- **BR-040:** Client delegated tolerance choice. Initial developer-selected
  default: configurable rounding-review threshold of 0.01 DOP and 0.01 EUR.
  Mark differences within the threshold as rounding candidates, retain the exact
  difference, and require explicit confirmation of nonzero discrepancies. Do not
  auto-reconcile, auto-write-off, or silently modify bank/sales amounts.

## Historical migration and routine imports

- **BR-022:** Provide a historical migration workflow for enriched tables and a
  routine workflow for source exports. Recognize the existing workbook and
  support column mapping for other historical layouts.
- **BR-023:** Migration includes original movements and existing descriptions,
  operation dates, expense periods, studios, methods, terminals, categories,
  notes, and review flags when present. Record imported manual values as such.
  Original bank exports cannot supply those missing business assignments.
- **BR-024:** Match imported locations to existing studios. Propose missing
  configuration for confirmation rather than silently creating duplicate
  studios or accepting unknown names.
- **BR-025:** Before commit, preview counts/totals by period and studio, existing
  matches, missing fields, and conflicts. Keep invalid or ambiguous rows in an
  actionable review state while importing valid independent rows. Structurally
  unreadable files or invalid account/currency contexts require correction.
- **BR-026:** Manual assignments outrank automatic suggestions. A blank later
  upload does not erase existing assignments. Conflicting explicit source or
  manual values require review. Preserve change history and origin.
- **BR-027:** Migration is intended as an initial transition but is safe to retry.
  Later overlapping bank uploads must recognize migrated movements. Missing
  identifiers or balances may require manual overlap review.
- **BR-028:** An imported `Conciliado` flag can preserve reviewed status. It only
  establishes a specific collection match if the source can reconstruct that
  relationship; otherwise it does not invent sales-to-deposit links.
- **BR-035:** Support report uploads and manual creation of financial movements.
  Show immutable creation origin (manual, routine import, or historical migration)
  and report name/batch when applicable. Manual edits to imported records retain
  import origin and add edit history. A later imported counterpart of a manually
  entered bank movement must be linked/reviewed without creating a duplicate.
  Do not fabricate a verified balance for manual cash entries.
- **BR-036:** Historical coverage: Dominican records begin January 2026; Spain
  expenses begin mid-2025 (exact first month not supplied) and income begins
  February 2026. Track actual imported coverage per source; an expenses-only
  period is not proof of zero sales or a completed monthly loss.

## Financial access

- **BR-029:** Financial access is explicit and separate from operational money
  visibility. For v1, extend the existing group/user capability system and reuse
  the user's existing allowed-site/studio limits. Check both the finance action
  and location/account visibility. `can_view_money` alone does not grant finance
  access. This replaces the earlier proposal for separate scoped finance roles.
- **BR-030:** A studio user cannot infer a shared bank account's full balances,
  other studio data, unassigned company movements, or original source files from
  studio access alone. Enforce access on APIs, exports, aggregates, previews,
  downloads, and reconciliation writes.
- **BR-031:** Groups define the usual capability set; users can receive additive
  grants. Combine grants by OR, as in the existing system. An unchecked user
  capability does not revoke a capability inherited from a group. Show the
  effective permission and its group/user origin. Group editing and assignments
  use existing user-management authority. V1 has one effective finance capability
  set within the user's existing location limits; different action levels per
  studio and explicit per-user denies are deferred. Sensitive-category rules are
  defined in BR-037. Developer-selected technical policy: Django superusers retain
  full administration; ordinary Admin membership alone grants no new finance
  capabilities. No real user grants are seeded without an explicit assignment.
- **BR-037:** Add an editable sensitive-category/subcategory flag and explicit
  `can_view_sensitive_finance` capability in the existing group/user system.
  Recommended first implementation: users without it see authorized category
  totals and their effect on results, but not individual sensitive payment rows,
  names, descriptions, notes, or identifying source details. This is stronger
  than hiding description alone, which can leak identity through other fields.
  Protect API details, search, exports, reconciliation candidates, audit history,
  and raw downloads containing sensitive records. Offer safe aggregates/exports
  instead. Sensitivity inherits from a marked parent category; do not let a
  subcategory silently weaken it. Changing sensitive flags or reclassifying a
  sensitive record requires sensitive-detail access plus the relevant write
  capability, preventing a user from removing a category to reveal its details.
  Existing location/action checks still apply.

## Confirmed follow-up policies

- **P-001 (Q-002, accepted 2026-10-24):** Show internal movements separately in bank/cash movement
  reporting. Exclude principal transferred within the same company from sales,
  expenses, and operating/final profit. Associated fees remain separate expenses.
  Transfers between distinct companies or to owners are not automatically
  internal transfers; treatment remains in Q-005.
- **P-002 (Q-003, accepted 2026-10-24):** In management results, start with gross sales and deduct
  estimated withheld processing fees once, plus distinct actual bank charges.
  Adjust estimates if actual processing fees later become available. A rule and
  a bank-charge row representing the same economic fee must not count twice.

The client explicitly accepted both policies on 2026-10-24. Fee allocation timing
and changes to closed periods still need their phase-specific definitions.

## Accounts without bank statements

- **BR-041:** Savings can be configured without routine statements. Retain a
  nullable reference opening balance and date; zero must be explicit. Confirmed
  DR savings baseline: 0.00 DOP at start of 2026-01-01. Later internal-transfer
  processing should derive an expected destination balance from known movements,
  without fabricating a bank-confirmed receipt. Link eventual counterpart evidence
  without counting twice. Source verification and missing balances remain visible.
  No expected-balance calculation exists in Phase 2.1.

## Reference reports

These are source fixtures, not committed datasets. Keep originals outside Git and
use minimized/anonymized test fixtures that preserve the relevant relationships.

| Source | Observed reference facts |
| --- | --- |
| `Ingresos_Egresos_DO_BI.xlsx` | Seven-sheet enriched workflow; historical migration reference; limited sample is not a full month's results |
| `Banco Popular Dominicano 1 al 15 Sept Deb. y Credit.csv` | September 1–15, 2026; 100 credits and 75 debits; several legitimate same-looking payments |
| `Alegra - Facturas - Beness Pilates Studio S.R.L. --10.csv` | September 1–15, 2026; 456 item rows, 438 invoices; total once per invoice DOP 2,574,587.60; cp1252 and semicolon-separated |
| `Caixa_20261007.csv` | July 1–October 7, 2026; 154 movements; signed EUR amounts; 77 terminal descriptions with DDMM operation dates |

Observed file contents describe these samples. Generalize only after validating
other layouts and agreed exception cases.
