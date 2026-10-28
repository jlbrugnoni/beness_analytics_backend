# DR Operational Finance — V1 release plan and readiness

Updated2026-10-28 (local date). Work remains on `feature/finance-phase-2` in both
repositories. This is a development delivery and release checklist, not production
approval or certification of a complete reporting period.

## Agreed release sequence (D-087)

1. **V1: Dominican Operational Finance.** Bank/report imports, actual bank/cash
   income and expenses, classification, daily/monthly closures and operational checks,
   correction/recovery and an accepted real reporting cycle.
2. **V2: include Spain.** Validate Caixa plus the Mindbody sales bridge and Spain's
   daily operating workflow. Spain is not a blocker for V1.
3. **Financial Analytics.** Management results, administration allocation, expense
   BI, income trends, graphs and dashboard integration begin after V2.

Verified running balances, paired account-transfer workflows and enforced month locks
are not V1 promises. Correct internal-movement classification and exclusion from
customer collections remain mandatory. No multi-day deposit splitting is introduced.

## V1 work delivered in this increment

### O-1: bank overlap recognition

Superseded/extended by D-088: use bank date, amount, description and balance as
primary evidence; Popular terminal/party serials and generic references no longer
independently imply identity. See BANK_MATCHING_V4_DELIVERY.md for the currentv4
matcher, direct pending-review UI and safe recovery of already imported reports.

Comparison-only whitespace normalization leaves raw descriptions and original ledger
facts unchanged. Unique compatible same-day amount/balance historical evidence can
outrank weak serial/terminal reuse across days. Separate equal receipts with different
balances remain separate. Equal indistinguishable occurrences and substantive
conflicts remain reviewable. Candidates with compatible date/amount/currency/direction
are presented before weak alternatives. Matching plan version advances tov3 so old
previews cannot be committed under changed matching rules without refresh.

Live bank batch20 now identifies8 of its10 pending rows as unchanged-compatible:
source lines13–18,20,22. The saved10 decisions themselves have **not** been resolved.
The2 remaining debit cases (lines115/116,20,000.00 and75.00DOP) need identity review;
report descriptions match workbook business descriptions but differ from original
source descriptions. Do not rewrite historical facts to make those differences vanish.

Isolated-copy rehearsal through the normal upload/processing/commit API used the real
stored September1–15 report:173 existing occurrences linked,2 held for review,
**zero new money movements**, all493 movements and every classification unchanged.
The original working database was not used for this posting. Private evidence:
`/private/tmp/finance-dr-rehearsal-*/rehearsal.json` (disposable local diagnostic).

### O-2: operational daily closure checks

An authorized reconciler can mark a company/day/payment method **Checked**, reopen it,
and inspect audit history. This is a review of the current assigned evidence, not a
hard month lock, invoice allocation, balancing entry or write-off. Individual source
`reconciled` flags remain unchanged. Existing incomplete import/classification queues
stay open; a checked day must not imply complete report coverage.

Exact differences need no mandatory comment. Every nonzero difference requires a
reason, including rounding-sized differences; all actual financial amounts remain
unchanged. Unknown expected fees must be resolved before checking. Studio-filtered
views remain read-only for checks; confirmation is company-wide for the five methods.

Snapshots retain daily totals, supporting record IDs/revisions/source hashes, invoice
revision and effective fee evidence. Changed receipts, links/assignments, invoice
revisions or fees produce **Needs recheck** dynamically. Unrelated days do not change
an otherwise identical check. Partner edits remain possible; refresh exposes stale
checks. Reopen/recheck is audited and stale submissions fail409. Repeated identical
checks do not create duplicate events. `can_reconcile_finance` is required, in addition
to existing money, finance, sensitive-detail and full-account company access.
No grants or credentials were changed for this delivery.

Models: ClosureCheck (unique company/day/method), ClosureCheckEvent (append history).
Migration0018 adds these tables only. API:
- GET `/api/finance/closures/`: existing comparison plus check status/tokens/counts.
- POST `/api/finance/closures/check/`: fresh evidence token/revision, optional/required reason.
- POST `/api/finance/closures/reopen/`: revision-checked reopen.
- GET `/api/finance/closures/history/`: scoped, paginated before/after audit history.

### O-3: historical cash correction/recovery

Initial setup → Cash income migration now offers **Undo cash migration** and
**Restore undone cash entries**, with a preview, protected counts and required reason.
Only selected-account entries originating from that workbook's company/file are in
scope. Exact copied previews share source identity; this does not undo another
company's or account's cash records.

Undo deactivates unchanged imported receipts; it never deletes originals or history.
Restore reactivates the same IDs/source keys, not new duplicate entries. Later edits,
linked/reconciled/checked receipts and inaccessible ownership remain protected.
Restoring detects possible overlaps against other cash/manual sources and respects
current account studio boundaries. A checked receipt requires reopening its check
before recovery. Source and classification snapshots, reason/actor and all changes
are audited. Retrying/stale previews cannot double-apply a recovery.

Use undo followed by the corrected historical workbook to correct a mistaken initial
cash migration; protected later work must be reviewed first. Cash import facts remain
read-only, and routine imports/manual entries are unaffected. Import+edit permission
and import ownership or finance-settings authority are required. API:
GET/POST `/api/finance/migration-imports/{id}/cash-recovery/`, mode undo/restore.

## Validation and preservation

Fresh PostgreSQL finance regression suite and frontend lint/build results are recorded
in Progress. Tests cover identity normalization/duplicates, check idempotence, changed
sources/fees, differences/permission gates, reopening/audit, cash undo/restore identity,
protection and manual-overlap detection. Financial tests run in disposable databases.

Before applying0018 to persistent local QA, an integrity-checked SQLite backup and
hash manifest were saved privately at:
`.local-backups/before-operational-checks-20261028T012317Z/` under the project root.
All33 preexisting finance tables matched their hashes after migration. Existing
movement/invoice/payment records, manual entries and saved import decisions were
preserved. New check tables start empty. No real day was marked checked and no real
cash import was undone by the developing agent during this delivery.

## Client acceptance tests for this increment

1. Refresh August closures. Open Cierre/August1 (expected and actual73,957.60).
   Open **Check day**, mark checked without a comment, and inspect history.
2. Open a day with a nonzero difference. Verify a reason is required and that checking
   it records the reason without changing its amounts. Reopen a check and inspect audit.
3. On a disposable/appropriate record, change an operation date/method or amount
   through its authorized workflow. Refresh: affected checks need rechecking. Keep
   legitimate client entries; do not delete records merely to manufacture a test.
4. In historical Cash income migration, inspect Undo/Restore previews. Edited and
   checked records must be protected. Exercise recovery only on a deliberately
   disposable migration in a separate company/test dataset, or after an agreed backup.
5. Refresh the September bank import review. Inspect8 newly recognized candidates
   and the2 remaining debit identities. Link only after reviewing the source evidence;
   retain historical classifications/originals.

## Remaining V1 release gates

2026-10-28: client accepted actionable closure review (issue filters and direct
supporting-record editors). See CLOSURE_REVIEW_WORKFLOW.md. This acceptance does
not certify that every September assignment or monthly difference is resolved.

2026-10-27 follow-up: client confirms daily check/reopen works; requested history
presentation refinements are complete. Seven additional closure access tests plus
the existing closure/check suites passed (20 tests) in disposable PostgreSQL.
See [OPERATIONAL_ACCESS_VALIDATION.md](OPERATIONAL_ACCESS_VALIDATION.md) for the
verified permission matrix and real-profile acceptance steps. Actual partner profile
acceptance and the other gates below remain pending.

- Client acceptance of O-1/O-2/O-3 and representative create/edit/void/review workflows.
- Normal September invoice/items CSV and transaction/payments XLSX are now uploaded
  as sales10/payments10. Both arrival orders/overlaps/repeats passed isolated actual-
  source rehearsal on2026-10-28:611 invoices,615 payments,4 split invoices and equal
  gross totals. D-089 corrects138 false legacy-text overlap anomalies and6 exact
  September customer links through scoped, audited recovery. Client accepted the
  recovery; saved results verified2026-10-28:470 creations/141 links/0 pending,
  all615 September payments linked. Full-month operational acceptance remains.
  See ALEGRA_SEPTEMBER_ACCEPTANCE.md. Actual sample has no cancelled invoices;
  cancellations remain regression-covered and need representative owner acceptance.
  Compare final monthly closures/classifications with the client's current document.
- September14–30 bank report21 is now present. Its53 overlap links are correct;
  D-088 corrects85 false holds caused by recurring identifiers. Disposable-copy recovery
  preserved prior work and a repeat upload recognized170 rows without new money.
  Client recovery/repeat upload accepted and audited2026-10-28: report21 has117
  creations/53 reused overlaps; report22 links the same170 movements and creates0.
  See SEPTEMBER_BANK_DUPLICATE_ACCEPTANCE.md. Resolve the2 remaining
  historical debit identities and saved pending
  decisions through normal review; do not treat improved candidates as completed decisions.
- Validate a full DR operating cycle and month against Excel, including real cash,
  fees, internal movements, refunds/reimbursements and missing-data queues.
- Validate real partner profiles, import/edit/reconcile separation and denied
  company/studio/sensitive access. No new grants without the owner's choice.
- Rehearse the production cutover in a separate dataset, with agreed historical
  cutoff, source versions and an inventory distinguishing real manual entries from
  disposable test entries. Do not reset the working data without explicit scope.
- Prepare an approved production database/file backup, actual legal company/studio/
  account mappings (never ship QA companies/fixtures), fee settings and import sequence.
  Deploy compatible backend/frontend plus migrations with finance visibility controlled.
  Check health/login/access, counts/totals/history and repeat-upload behavior before
  enabling the release for partners.
- Record production backup/restore and code rollback steps. On an issue, restrict
  finance access/feature visibility and preserve audit data; do not drop review tables
  or erase financial records as a rollback shortcut. Merge/push/deploy only when requested.

After these gates, V1 can be released without waiting for Spain or analytics.

See [BANK_MATCHING_V4_DELIVERY.md](BANK_MATCHING_V4_DELIVERY.md) for D-088 matching
rules, audited recovery, verification and client acceptance steps.
