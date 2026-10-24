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
