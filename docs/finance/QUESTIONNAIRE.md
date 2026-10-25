# Finance consolidated business questionnaire

Issued: 2026-10-24. Status: all 12 and the three focused clarifications answered.

The client requested one numbered list instead of separate question prompts.
Answer using the numbers below; brief answers or "recommend a default" are fine.
Do not include credentials or full account numbers. This questionnaire collects
remaining business definitions; it does not reopen accepted tax, internal-transfer,
fee-estimation, allocation, or group/user permission decisions.

Numbers identify this questionnaire only. Preserve Q-001–Q-006 in Discovery and
record each received answer under the corresponding original topic. Earlier
scattered prompts are consolidated here, not treated as answered or withdrawn
business requirements. Later phase-specific questions may still be needed after
sample validation; the client does not need to decide routine technical details.

1. **Accounts.** Which bank and cash accounts should we configure initially?
   For each, provide a label, company/country, currency, and studios served.
   Include the Dominican operating/savings accounts and Spain's Caixa account.
2. **Cash records.** How do you currently record cash expenses and cash retained
   at each studio? Do you want v1 to track a cash balance per studio, or initially
   just cash income, expenses, and deposits? If balances matter, can you provide
   an opening balance and date later?
3. **Historical migration.** From which month/year should we import existing
   enriched records? Will the initial migration cover both countries, and which
   periods already have sales plus bank/expense records available?
4. **Categories.** Should we use the Dominican workbook's category/subcategory
   lists as the starting taxonomy for both countries, or does Spain need a
   different starting list? Lists remain editable either way.
5. **Separate AZUL debits.** Do you know what the AZUL debit entries represent:
   additional fixed/service fees, adjustments to withheld fees, or something
   else? If unknown, we can leave those charges for review until identified.
6. **Spain processing fees.** Does Caixa deposit the full terminal sales amount
   and charge fees separately, or withhold fees from each deposit? Is
   T.PlanaMyCommerce the relevant terminal fee, and are there other payment
   channels/providers used in Spain?
7. **Spain sales source.** What is the exact Mindbody report you currently use
   for Spain collections? Does it identify payment methods, refunds, and payments
   split between methods? We will check it against the existing importer.
8. **Refunds and cancellations.** How are customer refunds and cancelled sales
   recorded in Alegra/Mindbody today? Should a refund reduce the management
   result in the refund month or amend the original sale month? How are the
   returned funds recorded when paid through a different method?
9. **Other movements.** How do you currently present loan receipts/repayments,
   partner contributions/withdrawals, large equipment purchases, and tax
   payments in the result table? Are they ordinary expenses/income, separate
   lines below operating result, or excluded from profit? Examples or a request
   for a proposed classification are enough; ordinary own-company transfers
   are already defined and do not need another answer.
10. **Sensitive detail.** Do payroll amounts, employee payment details, or
    customer details need additional restrictions beyond finance permissions
    and allowed sites/studios, or is that existing-style access sufficient
    for the partners using v1?
11. **Month closing.** Who should be permitted to close/reopen a month? Should
    unresolved classifications/reconciliation differences prevent closing, or
    can an authorized person close with a recorded explanation? If corrected
    reports arrive later, should changes require reopening that month?
12. **Reconciliation tolerance.** Do you currently accept small rounding or fee
    differences as reconciled? If so, what tolerance should apply in DOP and
    EUR? We can default to requiring explicit review of every nonzero
    difference until a tolerance is agreed.

## Discovery mapping

| Numbers | Topic | Used before |
| --- | --- | --- |
| 1 | Q-001 account inventory | Phase 1/2 account context |
| 2 | Q-002 cash lifecycle | Phase 4 cash workflow |
| 3 | Historical migration scope | Phase 3 migration/pilot planning |
| 4 | Category configuration | Phase 2 taxonomy |
| 5–6 | Q-003 fee evidence and provider rules | Phase 2/5 fee setup and reconciliation |
| 7 | Q-006 Mindbody source validation | Spain reconciliation integration |
| 8–9 | Q-005/Q-006 exceptional movement/result behavior | Phase 4/5/6 |
| 10 | Q-004 sensitive-detail policy | Phase 1 access acceptance |
| 11 | Period control | Phase 6 closing |
| 12 | Settlement policy | Phase 5 reconciliation |

## Answer register received 2026-10-24

| Number | Client answer and selected interpretation | Status |
| --- | --- | --- |
| 1 | Define DR first; developer to recommend account name. Proposed initial editable label: Banco Popular - Cuenta operativa (DOP). No real account created. | Direction accepted; later configuration remains editable |
| 2 | Manually type expenses as well as bulk-upload bank reports. Every record needs manual/import origin and imported report name. No explicit requirement to maintain verified studio cash balances yet. | Accepted, BR-035 |
| 3 | DR history from start of 2026; Spain expenses from mid-2025 and income from February 2026. Exact first Spain expense month not supplied. | Accepted, BR-036 |
| 4 | Seed existing categories/subcategories; edit names and create new entries in the app. | Accepted, BR-002 |
| 5 | Separate AZUL debits unknown; leave for review. | Resolved as review behavior, BR-039 |
| 6 | Caixa first-year terminal offer charges fees then reimburses them by separate credits; preserve both movements. Exact offer dates and other provider settings are later configuration. | Accepted, BR-039 |
| 7 | Mindbody Sales for Spain in v1, Alegra for DR. Alegra is the future Spain target after registration improvements; no cutover assumed. Consumer invoices may lack customer names. | Clarification accepted, BR-008 |
| 8 | Refund reduces result in original sale month, so refunded sale is not counted as income. | Accepted, BR-038 |
| 9 | Final = operating + extraordinary inflows - extraordinary outflows; loan receipts increase final management result only. Revenue-related taxes are non-operating; employment taxes are operating. Custom result is not yet a defined EBITDA metric. | Clarifications accepted, BR-020 |
| 10 | Add sensitive/private category flag; keep totals visible but restrict specific item/description. Developer recommends aggregate-only sensitive detail for users without an extra capability. | Direction accepted; design selected, BR-037 |
| 11 | Prepare for month closing but use later while adapting to the app. Interpreted as no enforced closing in initial v1. | Deferred, BR-021 |
| 12 | Developer to recommend tolerance. Selected configurable 0.01 DOP/EUR rounding-review threshold; retain differences and require explicit confirmation. | Developer-selected default, BR-040 |

## Focused clarification answers received 2026-10-24

- Spain: "let use mindbody for spain for now".
- Final formula and loan example: "Yes, use that formula and treatment".
- Tax boundary: only revenue-related taxes are non-operating; employment taxes
  remain operational because they are part of operations.

The main business discovery batch is resolved. Configuration values and detailed
source/edge-case checks belong to their implementation phases; do not ask the
same settled questions again.

Account names, provider dates, and other initial configuration can remain editable;
do not use missing setup values to block independent foundation work.

## Phase 2 configuration questions — 2026-10-24

Status: answered by client on 2026-10-24. Phase 1 accepted (D-027).
Previously accepted business policies remain unchanged.

1. Which Dominican accounts should initially be configured? Suggested editable
   labels: Banco Popular - Cuenta operativa (DOP), Banco Popular - Cuenta de
   ahorro (DOP), and studio cash accounts where needed. Account numbers are not
   required; missing values need not block configuration development.
2. Which Dominican terminals should map to which studios? Terminal identifiers
   and studio names are sufficient. Spain's 369092994 -> Estepona is already
   confirmed and is not being asked again.
3. Which processing fee rates apply to Dominican payment methods, and from what
   dates if known? Include fixed charges if applicable. Unknown rates remain
   unconfigured and flagged for review; never assume a zero fee.

No new code or production configuration is created by this questionnaire.

### Phase 2 answers received

1. Operating/savings names accepted. Savings has no routine reports but needs an
   expected balance; initial 2026 balance was zero and migration has transfers.
2. Eight DR terminals supplied; exact table in INITIAL_CONFIGURATION.md.
3. Cierre/Recurrentes 3.5%, Link 5%; rates apply throughout available history per
   client ("since forever"). No fixed fee supplied.

See Q-007, D-028–030 and BR-041. No further account/terminal questions are pending.

## Phase 2.2 category questions — Q-008, 2026-10-24

Status: answered 2026-10-24. See PHASE_2_2_DISCOVERY.md for the extracted
10-category/44-subcategory catalog and the basis for each recommendation.

1. Independent catalogs per company, with explicit copying later?
2. Start sensitive with entire Personal plus Administracion / Sueldos
   administración and Seguridad social administración? Any additional restrictions?
3. Ordinary expenses operating, revenue-related Impuestos extraordinary,
   Equipamiento/Intereses/Devoluciones requiring review until movement classified?
4. Use explicit paired catalog plus Otros / Extraordinarios; invalid 1 / 1
   remains a migration review item?

Answers: (1) yes, with the aim of matching categories across all companies for
comparable analysis; (2) agreed, no additions; (3) agreed; (4) agreed.
See D-032–035. Phase 2.2 has no remaining discovery question.

## Phase 2.3 mapping questions — Q-009, 2026-10-24

Status: answered 2026-10-24. See PHASE_2_3_DISCOVERY.md.

1. Do generic Alegra Tarjeta crédito/Tarjeta débito labels also include Link or
   Recurrentes? If so, recommend pending channel review rather than assuming Cierre.
2. Are Efectivo/Transferencia reliable for direct mapping, or also review-only?
3. Which exact Spain Mindbody method names map to terminal/recurring/link/transfer/
   cash? If not available now, leave Spain aliases editable and unconfigured.

Existing cost-center precedence, General neutrality, terminals and fee rates
are already decided and are not being asked again. No proposed trust default
is considered approved without a response.

### Phase 2.3 answers received

1. Alegra Tarjeta débito maps to Link; Tarjeta crédito normally maps to Cierre.
   Recurring also uses Tarjeta crédito and needs manual distinction.
2. Efectivo and Transferencia map directly, as above.
3. Spain normally uses in-studio card and cash; no recurring or transfer payments.
   Exact Mindbody labels were not provided. Keep aliases editable/unconfigured.

D-037–038 supersede the proposed fully unassigned generic-card default. No
additional question blocks Phase 2.3 configuration/preview development.

## Phase 2.4 questions — Q-010, 2026-10-24

Status: answered; exact Caixa terms remain unknown and editable.

1. In Spain, does Caixa deposit the full card-sales amount and charge terminal fees separately, or deduct anything from each deposit?
2. What is Caixa's fee arrangement (monthly amount, percentage, or both), and when does the first-year reimbursement offer start/end? Unknown settings can remain pending rather than zero.
3. For DR Cierre, Recurrentes and Link, do deposits normally arrive within the previously mentioned 24–48 hours? Do weekends delay them? Timing guides suggestions; operation dates remain editable.

### Q-010 answers received — 2026-10-24

1. Caixa deposits the full card amount and charges its terminal fee independently,
   later returning that fee (D-040).
2. Fee is somewhere near EUR 36; offer ends in 2027. Exact amount, frequency and
   dates remain unspecified. Keep these structured values unknown and preserve
   the approximation/year in notes. They do not block generic configuration.
3. DR normally takes 24–48 hours, sometimes longer on weekends (D-041).

No further answer blocks Phase 2.4 configuration. Exact Caixa terms remain an
optional configuration follow-up, not guessed defaults.

## Phase 3 questions — Q-011, 2026-10-24

Status: answered (D-043–046). Exact pilot month remains Phase 3.4 preparation.

1. For bank reports, do you usually download the whole month again, only new
   dates, or overlapping periods? Does this differ between Popular and Caixa?
2. For Alegra exports, do you always include every invoice item for the selected
   dates, or sometimes filter by product/category/payment method? This affects
   recognizing corrected invoices without removing valid items.
3. Which period should be the first historical migration test? Recommend one
   completed DR month with classified workbook entries and raw bank/Alegra reports
   so totals can be compared. Existing September 1–15 samples still support
   adapter validation; a full-month pilot is a separate choice.
4. Should an upload made by mistake support audited undo? Proposal: undo untouched
   records created by that upload; require review for later manually edited or
   reconciled records; preserve existing records merely encountered again.

### Q-011 answers received — 2026-10-24

1. Popular downloads are normally daily due to volume; overlapping reports are
   allowed to ensure all information. Caixa downloads occur every several days.
   Do not assume a daily file excludes previously seen dates (D-043).
2. All Alegra invoices are downloaded without the proposed filters (D-044).
3. Client agreed to a completed DR month for migration comparison. Exact month
   and cutoff remain to be chosen during Phase 3.4; none was named (D-045).
4. Client accepted the proposed audited undo boundaries (D-046). This is future
   financial commit/undo behavior; preview history stays immutable.

No further business answer blocks bank-preview development. Exact pilot month
and source-update reversal cases remain phase-specific follow-up.

## Phase 3.2 questions — Q-012, 2026-10-24

Status: answered; both recommendations accepted (D-049–050).

1. Who may undo another user's import? Recommend operators undo their own;
   users with Manage financial configuration can undo others' imports too.
   Relevant import/edit permissions and full account access remain required;
   edited/reconciled record safeguards apply to everyone.
2. If a later bank report appears to correct an existing transaction's amount
   or date, should replacement require review? Recommend preserving the existing
   transaction and displaying the proposed correction for approval, while
   independent valid new rows can still import.

### Q-012 answers received — 2026-10-24

1. Yes: proposed own/other import undo authority accepted, with all existing
   capability, account and protected-record safeguards (D-049).
2. Yes: preserve existing amount/date until explicit correction review, while
   independent valid new rows import (D-050).

No further business question blocks bank transaction posting/review/undo.

## Q-013: Phase 3.3 Alegra questions — 2026-10-25

Status: answered 2026-10-25 (D-052–055); exact cancelled-status text pending.
Phase 3.2 accepted (D-051). See PHASE_3_3_DISCOVERY.md.

1. Can an invoice number ever be reused in another year or numbering series, or is the full number unique within the company? If you use several series, does the exported number include the prefix?
2. When a later export changes an existing invoice's date, amount or items, should the app keep the current invoice and ask you to approve the complete updated version? I recommend this, preserving its previous version and manual assignments, and flagging assignments affected by changed items.
3. Can one invoice be paid using two methods, such as part cash and part card? If yes, does your Alegra export show the amounts for each method, or do you record that split elsewhere?
4. When an invoice is cancelled or refunded, does it remain in this export with a status, disappear, or appear in a separate credit-note report? If you do not know, we can leave those cases for review until we have an example; a missing invoice will never be treated automatically as cancelled.


### Q-013 answers received — 2026-10-25

1. Full invoice codes should not repeat within either company. Dominican series
   begin B01/B02 followed by eight digits. Keep company/source/full code identity,
   including prefix, rather than year-based reuse (D-052).
2. Yes to approval of changed source evidence, but Alegra currently allows only
   cancellation, not edits to invoice date, amount or client. Treat such changes
   as anomalies, retain the original and require investigation rather than offering
   ordinary edits to those values. Cancellation/status approval remains a later
   posting workflow (D-053).
3. No mixed payment methods in the current workflow. One or two cards can fund one
   invoice at the same moment; bank settlement is the whole day's card deposit.
   Do not require a split per card or assume card count changes invoice totals
   (D-054). Partial/grouped settlement matching remains Phase 5.
4. Cancelled invoices remain in the export with a cancellation status. The refund
   happens later as a bank debit. Preserve both events, remove the sale's result
   contribution in its original month and do not deduct the same refund twice
   (D-055, BR-038). Exact cancellation text in ESTADO is still pending: the sample
   contains only Cobrada. A focused asynchronous question requests that text.

First delivery: Phase 3.3.1 source previews. Invoice posting, approval of changed
statuses and refund reconciliation follow after preview review. This subdivision
keeps unconfirmed cancellation labels from being guessed.
