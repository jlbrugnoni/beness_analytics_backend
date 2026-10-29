# Monthly closures comparison — C-1 delivery

Current extension: [DR Operational Finance V1](DR_OPERATIONAL_RELEASE.md) adds audited
daily checks/reopen and cash recovery. The read-only API restrictions below describe
the original C-1 checkpoint; the extension is the current implementation.

2026-10-27. Local development branches only; client acceptance pending.

## Business definition (D-085)

Client compares all days of a selected month and accumulated totals, separately for
Cierre, Transfer, Cash, Recurrentes and Link. Expected income comes from Alegra's
payments report less the fee for that payment method. Actual income comes from
recorded bank/cash receipts. Client does not split deposits across operation days.

Implement a compact monthly summary by method, opening a dialog with every day,
monthly totals and accumulated difference. Keep one assigned operation date per
actual receipt. No deposit splitting or automatic reconciliation is introduced.

## What changed

A **Closures** navigation item opens `/finance/closures`. Select company, month and
optionally studio. The summary has expected receipts, actual bank/cash receipts and
difference for each of the five methods. Difference is **actual minus expected**.
There is no combined-all-method success indicator that could mask opposing errors.

Click a method to see every calendar day, including days without recorded activity,
with Alegra payments, estimated withholding, expected receipts, actual receipts,
daily difference. Month totals, including the full monthly difference, appear at
the bottom. The running accumulated-difference column was removed by D-086.
Click a date to inspect supporting invoice payments and actual receipts. Review and
excluded-movement queues are separately accessible with paginated evidence.

The screen compares available records; it does not prove source coverage, validate a
cash/account balance or mark anything reconciled. Zero amounts mean no included
records for that cell, not proof that the day is complete.

## Calculation and source rules

- Sum each active valid posted **Alegra payment** once, using its payment date and
  assigned method. Do not sum invoice total or item total per payment. Fractional
  invoice payments therefore contribute their individual amounts only.
- Invoice linkage/assignment warnings stay visible but do not erase a valid posted
  payment from company-wide expected receipts. This includes customer-name conflicts,
  missing invoice links and an invoice later cancelled. These are collection
  comparisons, not net sales/profit: original incoming payments remain evidence of
  money received; cancellation/refund result adjustments belong to the separate
  exception/result workflow. Cancelled payment exports are already rejected by the
  existing payment posting validation. No new source acceptance is introduced.
- Effective receipt studio follows the existing API: inherit invoice studio only
  when assignment origin is invoice; otherwise use the receipt's assignment.
- Actual receipts use the general money ledger, active incoming customer movements
  across visible company accounts. Use **operation date**, not bank transaction date.
  A September2 deposit assigned to August31 belongs in August. Cash uses independently
  recorded cash-account receipts, never an automatically generated invoice copy.
- Internal movements, refunds/reimbursements and extraordinary credits are listed
  separately and excluded from ordinary customer collections. Cash-method entries
  in bank accounts are held for review rather than treating a bank cash deposit as
  another customer cash receipt.
- Missing actual operation date or payment method, invalid financial facts and wrong
  source/currency are excluded from the relevant totals and surfaced for review.
  Actual entries with no operation date appear in the review queue for their bank
  transaction month; the app does not invent a date.
- Assigned records that still need review remain included provisionally. At company
  scope, records lacking a studio still contribute to their method/date; a selected
  studio contains only explicitly assigned/inherited entries for that studio.
- Gross values remain tax-inclusive. Cash/transfer default to no withholding if no
  fee policy is configured; explicit policies still apply. Card/recurring/link need
  one unambiguous effective fee policy. Full deposits with separate fees have zero
  withheld fee; separate fee charges/reimbursements are not deducted again.
- Estimate withholding from the selected scope's gross total **once per operation
  day and method**, using Decimal, ROUND_HALF_UP to2 decimals. Sum rounded daily
  estimates for the month. This is an estimate; per-terminal settlement rounding may
  differ. Studio-filtered rounding is independent, so studio totals may differ by a
  cent from rounding a company-wide daily total.
- Unknown/ambiguous fees produce `null` expected/difference, rendered as —; do not
  silently substitute zero. Monthly totals/accumulated values stay unknown from an
  unresolved estimate. BR-040 rounding review remains unchanged and is not used for
  automatic write-offs or confirmation in this read-only phase.
- Invoices without payment evidence and pending import decisions are flagged. There
  are no synthetic expected payments based on an invoice amount.

## Access, implementation and limits

GET `/api/finance/closures/?company=...&month=YYYY-MM&studio=...` returns five methods,
all daily rows and exact decimal totals. GET `/api/finance/closures/evidence/` accepts
optional channel/day/side and returns paginated supporting rows. Responses are
private/no-store. POST and other mutation methods are unavailable.

Reuse existing finance/money/sensitive-detail and bank-account access, company/site
scope, and the existing full-company workspace restriction. Partial studio-only users
cannot use this company-wide comparison yet. Require visibility of every company
account; never compare company-wide payment totals to a silently partial account set.
Foreign-company/studio selectors fail closed. Currency is explicit in evidence.

DR/DOP Alegra is supported first. Spain shows an explicit unavailable message until
the Mindbody sales integration is ready; it does not show fabricated zero expected
sales. No new permission, database model or schema migration is required.

There is no saved reconciliation/allocation, month lock, verified running balance,
actual-fee adjustment engine, bank overlap fix, automatic date assignment, source
coverage certification or monthly result calculation in this delivery. Existing
pending import decisions remain unchanged. Deposit splitting is outside the agreed
workflow. Future confirmation must retain source revisions/audit and support reopening
when evidence changes; a zero difference alone must not set booleans.

## Validation

- Fresh isolated PostgreSQL finance suite: **293 tests passed**, including8 closure
  tests for monthly/daily/cumulative math, daily rounding versus per-payment rounding,
  fractional payments, operation-date month boundaries/leap year, independent cash,
  exclusions, unknown/effective fee settings, pending evidence, access and no writes.
- Frontend changed-file lint, production build and migration drift checks passed.
- Browser verified August monthly totals, all31 days/month totals, cumulative
  differences, and the Alegra versus actual-receipt evidence filter. August1 Cierre
  shows76,640.00 payments,2,682.40 fee and73,957.60 expected/actual. The actual
  evidence comprises3 bank receipts dated August3 assigned to August1.
- Hash comparisons of all33 finance tables before/after browser/API checks were
  identical. Current working data remains493 movements,744 invoices,745 payments,
  including the client's manual entries. No reset, automatic posting or source
  rewrite. A private local preservation manifest is saved in
  `/private/tmp/finance-closures-preservation.json` (diagnostic, not a durable backup).
- Evidence can toggle All/Alegra payments/Actual bank-cash; the shared layout now
  permits the content flex item to shrink within its available width. The Closures
  route uses the existing financial-account capability gate.

## Month navigation and table refinement — D-086

Month selection now uses localized month names and a year dropdown, with previous/next
month arrows that cross year boundaries. There is no need to type a date. The year
menu follows the selected year (10 preceding and5 following years, within1–9999).
The daily table retains its daily difference and one monthly total at the bottom;
the running cumulative column and duplicate total have been removed from the UI.
Backend response fields are retained for compatibility; monetary calculations and
financial records are unchanged. Changed-file lint/build and browser checks cover
dropdowns, year rollover and the6-column daily table.

## What the client should test

1. Open Closures for the working company and August2026. Compare the method summary
   to the corresponding payment-report and receipt records, noting visible warnings.
2. Open Cierre. Verify3.5% estimated fees, all31 days, month totals and the total
   difference in the final row. Open Link and check5%; Cash and Transfer have no withheld fee by default.
3. Click a day and inspect individual payments and actual receipts. A split invoice
   must contribute each payment once, not repeat the invoice total.
4. Open Cash and verify the manual cash receipt appears on its operation date.
   A cash expense and internal bank deposit must not increase cash customer receipts.
5. Switch to September and optionally a studio. Verify bank transaction dates do not
   move receipts away from their assigned operation month. Check the review queue for
   entries missing operation date/method and invoice/link/import warnings.
6. Confirm that opening/refreshing the comparison changes no source facts, entries,
   review flags or reconciled flags. September coverage still depends on actual
   report uploads; do not treat current partial data as a completed reconciliation.
