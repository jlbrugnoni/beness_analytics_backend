# Invoice reopen and import performance

Investigated 2026-11-05 after an invoice reopen took 77 seconds in production
and invoice imports were slow. The production request timing was reported by the
user; the comparison below is a backend benchmark on a disposable copy of the
local finance database, without production network or lock contention.

| Operation | Before | After |
| --- | ---: | ---: |
| Reopen one reviewed invoice | 4.302 s | 0.018 s |
| Compute a 611-invoice posting preview | 0.428 s | 0.131 s |
| Post the same 611-invoice overlapping report | 4.611 s | 1.118 s |
| Database statements for overlapping report posting | 1,852 | 29 |

The copy contained 5,652 invoice records and 5,615 payment records. Posting
was measured with overlapping invoice evidence in a new preview; the benchmark
rolled back its writes. Receiving and saving the CSV as a new preview took
about 0.14 seconds locally, so the report comparison and posting were the
more significant work in this example. Absolute production timings are not
inferred from these local measurements.

- Reopening checks only the affected invoice's payment group, including waiting
  payments. It no longer recalculates unrelated groups or reruns company-wide
  historical supervision. Reopen still updates revisions and records audit events.
- Preview and posting load only overlapping invoice identities. Source column
  interpretation and active mapping rules are reused within the report.
- Posting batches invoice, decision, audit and payment-link writes. Link matching
  no longer selects the original source row JSON or import summaries for each
  ledger row. The existing company lock and transaction still protect posting.
- Invoice payment detail lists avoid loading source evidence that the response
  does not use. No permissions, review rules, duplicate checks, or schema changed.

After deployment, compare the reopen POST, sales import upload POST, processing
GET, and commit POST separately in the browser's Network panel. A long server
wait after these changes would warrant checking production database/lock timings;
the local test cannot measure those.
