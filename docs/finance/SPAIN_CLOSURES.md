# Spain V2 Step 3 — Mindbody / Caixa / cash closures

2026-11-15: implemented locally; owner testing pending. Step 2 accepted by the
owner's direction to continue. Work remains uncommitted on feature/finance-spain-v2
in both repositories. No deployment or production data changes.

## Behavior

Existing monthly/daily closure workflow now supports Spain/EUR as well as DR/DOP.
Spain expected collections use only the Mindbody adapter from Step 2: sum paid
amounts by sale date, effective payment method and effective payment studio. Do not
also count Alegra invoices or FinancialReceipt copies. Source amounts remain tax-
inclusive. Configured full card settlement gives zero withholding; independent
terminal fees and their reimbursements are separate ledger movements, not a second
card-withholding deduction. Unknown fee configuration stays unknown, not zero.

Actual collections use operation dates on bank/cash movements. A November bank
credit assigned to an October operation belongs in October's comparison. Bank date
remains visible in supporting records. Only actual cash-account receipts count as
received Cash; Mindbody cash sales provide expected collections and never create
cash receipt transactions. A cash deposit into a bank account is not another cash
sale. Internal movements, refunds/reimbursements and extraordinary credits remain
excluded from customer collections; debit expenses do not change this comparison.

Structural source errors and negative/refund groups stay excluded/pending for later
exception handling. Missing method/date and invalid facts remain actionable review
queues. Valid classified collections awaiting review remain included with warnings,
consistent with DR. A sale with an unknown date stays in the review evidence (using
its previous known date where available) rather than inventing a date or expected
amount. Coverage remains provisional; no balance, complete-period or reconciliation
certification is inferred. Original invoice/refund-result accounting remains Step 4.

UI defaults Spain's summary to Card/Cash and shows additional channels if activity
exists. All calendar days and a monthly total remain in each method dialog; no
per-row cumulative difference column is introduced. Source-neutral wording replaces
Alegra-specific labels in shared closures. Supporting Mindbody rows open the
Mindbody sale editor, while bank/cash rows retain the existing movement editor.

## Checks, source changes and permissions

Reuse existing daily operational checks, difference comments, chronological history,
privileged reopening and stale evidence tokens. A nonzero difference requires an
explanation to check the day. Checking does not mark individual source records
reviewed or reconciled. Company-wide checks require full account visibility and
existing money/finance/sensitive/bank scopes. Editing/checking uses can_edit_finance;
reopening uses can_reopen_finance. Studio-filtered views do not permit company checks.
Ambiguous active companies for the same Mindbody site remain rejected by Step 2's
source-authority guard. Other unsupported country/currency pairs remain unsupported.

Mindbody evidence IDs identify sale+reported method; fingerprints include source
facts, effective mappings, overrides and assignment revision. Unchanged overlapping
reports do not invalidate a checked day. Changed supporting sales/payments/receipts
or effective fee rules produce Needs recheck. An unrelated sale on a different day
does not invalidate that check. A checked day must be explicitly reopened before it
can be checked against changed evidence. No asynchronous source sync or extra sales
upload was added. No schema migration is needed for Step 3.

## Validation

- 448 finance tests passed on disposable PostgreSQL, including nine new Spain
  closure tests; 31 targeted closure/access/check cases also passed on SQLite.
- New cases cover full settlement, independent cash receipts, later bank settlement,
  excluded transfers/reimbursements/extraordinary credits, missing assignments,
  source changes/repeat stability, stale tokens, privileged reopening, studio and
  bank permissions, missing fee configuration and Mindbody drill-through metadata.
- Changed frontend files pass ESLint; isolated production build passed.
- No migration drift. Browser verified October overview,31 daily rows/month total,
  8 October supporting records, opening Mindbody sale1097 from that view, and safe
  dialog closure. Browser verification did not save any working transactions/checks.
- Local saved data: Card expected6692.60 / actual6732.09 / difference+39.49;
  Cash expected1841.65 / actual0.00 / difference-1841.65.
- Card differences match the supplied-file analysis: October8 +6.00;15 +19.49;
  19 +6.50;24 +7.50;26 +15.00;27 -15.00. These are observations for investigation,
  not approved corrections. Final October settlements may still require November
  bank reports; current equality/differences do not prove complete coverage.

## Owner tests

Open http://127.0.0.1:3037/finance/closures?company=3&month=2026-10 using QA spain
company. Keep Studio set to All when testing company checks.

1. Confirm the Card/Cash totals above. Card estimated withholding is zero.
2. Open Card -> View days. Inspect all31 days and total; October8 is304.00 expected
   versus310.00 received. Click the date and open a source sale and bank receipt.
3. Check October1 (1555.00 expected/received), reopen, and inspect chronological
   history. A day with a difference requires a comment before checking.
4. Records -> Income: create the general cash account if absent, then manually
   record a verified/test cash receipt such as129.00 on October31 for Estepona,
   Cash method and that cash account. Refresh closures: actual Cash increases129.00,
   expected Cash stays1841.65. This does not create or change Mindbody sales.
5. Optional: check a relevant day, correct a supporting assignment, then refresh.
   Expect Needs recheck and privileged reopening before checking again. Restore
   the correct assignment after testing. A repeated identical report stays stable.

Wait for owner acceptance and explicit commit/progression before Step 4. Historical
Spain migration requirements and real split/refund source samples remain Step 4;
financial analytics remains outside this operational release.


### Owner test follow-up: cash account mismatch

2026-11-15: owner created manual credit6062 for EUR12.00, operation2026-10-02,
transaction2026-11-15, methodCash, on the Caixa bank account. Company3 has no cash
account. Correctly excluded with cash_account issue; pending review is not the reason
for exclusion. Working entry was not changed. Added a manual-entry warning/disabled
Save and backend validation for Cash customer receipts on bank accounts; bank cash
internal movements remain allowed. Existing manual facts can be edited to move this
entry into a configured cash account.19 targeted money/Spain closure tests and
changed-file frontend lint passed. No commit/push. Owner should create general cash,
edit the existing entry account, and refresh October closures with Studio All.
