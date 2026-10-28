# Closure review workflow — DR operational V1

Delivered2026-10-28 on feature/finance-phase-2 in both repositories.

## Purpose and scope

Make missing-information queues usable from monthly closures. Existing financial
calculations, source protection, assignment rules, permissions and check/recheck
behavior remain authoritative. No financial record is automatically classified.

Click a record-level review indicator (for example Operation date missing or Payment
method needs review) to open only supporting rows with that issue. The existing
View records needing review button still opens every supporting row with issues.
Counts overlap: one receipt may need a date, studio and payment method. Pending
import decisions and missing fee policies remain separate summary issues; they are
not record-assignment queues and are not made into clickable record indicators.

Click a row's number to open its existing editor over the evidence list:
- Actual bank/cash income opens the movement editor, including operation date,
  studio, method, review status and authorized manual-entry corrections.
- A linked expected payment opens its invoice and linked payments. It uses the sale
  ID, not the receipt ID; original invoice provenance is retained separately from
  the payment report's provenance.
- A payment without an invoice opens payment details; an invoice without payments
  opens invoice details.

Closing an editor returns to the same queue/page. Saving refreshes the queue and
monthly/daily totals while preserving the selected month/method. The existing
check snapshots determine when corrections require rechecking. Source amounts,
bank dates, invoice numbers and clients remain protected by their normal workflows.
Import, correction, audit and permission endpoints are reused; this is not an
alternative authorization or posting path.

GET /api/finance/closures/evidence/ accepts an optional validated `issue` filter,
combined with existing company/month/studio/day/channel/side filters before
pagination. Existing full-company/account and sensitive-data gates remain in force.
Evidence now includes linked sale ID and invoice report provenance for navigation.
No schema migration is required.

## Validation and client tests

PostgreSQL regression verifies issue filtering, editor identities and provenance,
read-only GET behavior, invalid filters, denied access and an authorized operation-
date correction clearing the queue/updating actual totals without changing bank date.
Browser checks use read-only opening/closing of actual September records; no working
assignment was saved by the developing agent. Frontend lint/build and migration drift
are checked; final regression results are recorded in PROGRESS.md.

1. Open Closures, September2026, and click Operation date missing.
2. Open an income by its number. Verify original bank facts and existing studio/
   terminal/method are preserved. Close: the filtered list should remain available.
3. For an income whose operation date you know, enter that date and complete any
   required assignments. Save, close and verify it leaves the missing-date queue and
   updates its method/day total. A record can remain in other review queues.
4. Open a payment-method or invoice-review queue. Click a payment number and verify
   the correct invoice and linked payments appear; close without saving if uncertain.
5. Open a method's daily table, then a day and a supporting record. After a legitimate
   correction, verify refreshed totals and any Needs recheck status.

The initial read-only September audit had151 incomes missing operation dates,
46 missing methods,52 missing studios and157 unreviewed incomes. These are diagnostic
counts at that time, not fixed targets. Actual operation dates, transfer identities,
cash completeness and recurring-versus-terminal distinctions need owner review.
The old bank20 queue still had10 pending decisions; no automatic resolution is added.
Spain and analytical reporting remain later releases.
