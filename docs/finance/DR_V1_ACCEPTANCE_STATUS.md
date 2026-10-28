# DR operational V1 — acceptance checkpoint

**Dataset superseded by owner-authorized local reset2026-10-28.** Current records
are empty, ready for the supervised Jan–Aug baseline and September replay. See
RESET_JAN_AUG_2026.md. Values/queues below are evidence of the backed-up prior tests.

Date2026-10-28. This is a saved-data audit and client acceptance checkpoint, not
production approval, a financial statement or certification of full-month coverage.

## Accepted since the last checkpoint

- Direct closure review queues/editors: client confirmed they worked.
- September21 daily closure: client confirmed it worked. Saved Cierre evidence has
  10 expected payments,3 actual receipts,85,000.00DOP gross,2,975.00 estimated fees,
  82,025.00 expected,82,025.00 actual and0.00 difference. Check is current (Checked).
- Records > Income closes after a successful classification save: client accepted.

The client acceptance confirms those workflows. It does not confirm every payment
assignment, every method on September21 or all September movements.

## Read-only audit method

Created a consistent SQLite backup from the persistent local QA database through a
read-only source connection. Ran the existing closure/presentation functions with
SQLite query_only enabled on that disposable snapshot. No financial assignment,
import decision, profile, source file or check was written. Private diagnostic:
`/var/folders/4b/zlc0b2vd2_b9207mqqssy6l80000gn/T/finance-readiness-mb8ra0xa/audit.json`.
This path is local evidence only, not an application dependency or production backup.

Audit focuses on company1, QA financial company. Other QA fixture companies are
separate and are not added to its totals. Accounts include the operating bank,
savings, general cash and an additional Posting QA bank account: production setup
must explicitly distinguish actual accounts and disposable fixtures.

## September21 method comparison (DOP)

| Method | Expected after fees | Actual assigned to day | Difference | Check |
| --- | ---: | ---: | ---: | --- |
| Cierre | 82,025.00 | 82,025.00 | 0.00 | Checked |
| Transfer | 6,000.00 | 0.00 | -6,000.00 | Open |
| Cash | 4,500.00 | 0.00 | -4,500.00 | Open |
| Recurring | 0.00 | 0.00 | 0.00 | Open |
| Link | 4,750.00 | 4,750.00 | 0.00 | Open |

Zero actual here means no included actual receipt is assigned to that method/day;
it does not establish that money was not received. Expected amounts must never be
copied automatically into actual cash/bank records to make differences disappear.
Cierre still has payment/invoice review flags even though the numeric totals match;
a Checked day does not clear underlying source/assignment queues.

## Remaining September queues

Closure issue counts overlap and cannot be added as a unique-record count:

| Queue | Count |
| --- | ---: |
| Actual income missing operation date | 144 |
| Missing payment method | 46 |
| Missing studio | 52 |
| Unreviewed included/candidate customer income | 150 |
| Expected payment method review | 347 |
| Invoice assignment review (payment evidence rows) | 483 |
| Pending bank import decisions | 10 |

Month-wide invoice/payment imports have0 pending decisions. Bank pending decisions
are in report20; eight were recognized as compatible after matcher improvements,
but still need an explicit accepted link decision. The other two need owner identity
review. Do not infer approval from a candidate being ready to link.

The Records income list is a broader set than closure customer collections: by bank
transaction date September has164 active credits,157 needing some review. It can
include internal/refund/extraordinary entries and dates assigned outside the month.
There are129 September debits by bank date;127 still need classification (studio or
administration, category, expense period and review). That is expected unfinished
work after routine import, not proof of a failed historical-classification migration.
No September cash expenses were recorded in a cash account in this snapshot. The
only two manually created records are dated October; retain them until their purpose
is confirmed, rather than silently treating them as disposable fixtures.

## Configuration checked

Savings remains configured with0.00 opening balance at2026-01-01 and no expected
statements. General cash exists and does not expect bank statements. Active fees
are3.5% Cierre/recurring and5% Link, without date restrictions. Cash/transfer use the
existing zero-fee default. All eight originally supplied DR terminals are present;
an additional configured recurring terminal39618800005 (Arroyo Hondo) is also present.
Do not remove it automatically; confirm the complete actual production terminal list
at cutover. No fee-policy gaps appeared in this September comparison.

## Next client validation

1. September21 cash: check whether the4,500.00 was actually received. If confirmed,
   register the actual cash received in General cash, assigning studio and operation
   date from evidence. If an entry already exists elsewhere, investigate/correct that
   record instead of creating a second receipt. Compare and check the day afterward.
2. September21 transfer: locate the corresponding bank receipt using actual evidence.
   Assign the correct operation date/studio/method, or leave unresolved with the known
   reason. Do not create another bank income merely to match expected payments.
3. Test one real cash expense, with its actual account, category/subcategory, expense
   period and studio/administration assignment. Confirm it appears once in Expenses
   and does not become a negative customer collection in Closures.
4. Review an actual internal movement and refund/reimbursement if examples exist.
   They must remain visible as records and excluded from customer collections.
5. Before full-month acceptance, finish source coverage and classifications, resolve
   legitimate import decisions and compare the month against the complete document.

Representative actual cancellation, protected recovery and real partner access
acceptance still need suitable examples/profiles. Automated regression coverage is
already documented; do not manipulate production-like records just to manufacture
those scenarios. Production mapping, separate-dataset cutover rehearsal and approved
backup/restore remain in DR_OPERATIONAL_RELEASE.md. No new analytics or Spain scope
is introduced by this checkpoint.


## Follow-up: cash/transfer acceptance and date controls

2026-10-28: client confirms completing the requested cash/transfer/expense tests.
A new consistent read-only audit confirms September21 transfer6,000.00 and cash
4,500.00 now both match expected; Cierre82,025.00 and Link4,750.00 still match.
Cierre and cash are Checked; transfer and Link remain Open (numeric equality is not
an automatic check). Some underlying assignment/review flags remain. Previous audit
figures above are retained as a dated checkpoint, not the current day comparison.
Private refreshed evidence:
`/var/folders/4b/zlc0b2vd2_b9207mqqssy6l80000gn/T/finance-readiness-3cte7egu/audit.json`.

Current September queues still include143 missing operation dates,45 missing payment
methods and10 old bank20 decisions. Invoice/payment pending decisions remain0.
These counts overlap and reflect unfinished real-period review, not missing features.

Client requested easier operation-date/expense-period entry. Income assignment now
uses the native date/calendar input already used by record filters. A shared
MonthSelector provides localized month names, year dropdowns and previous/next-month
arrows for expense assignment, manual expense creation/editing and Closures. Missing
expense periods remain Unassigned until explicitly selected; either dropdown can
clear them. Selecting a month in an empty field uses the bank/entry date's year as a
reference; selecting a year uses its reference month. Existing saved values remain
unchanged on opening. The year range follows the current/reference year, as closures
previously did, and year boundaries are constrained to0001–9999. API values remain
YYYY-MM-DD dates / first-of-month expense periods; original bank dates are unchanged.

Browser verified an unassigned imported expense stays empty, selecting September2026
then the previous arrow displays August2026, and closing discards those unsaved
changes. Income date displays21/09/2026 with a working calendar popup. No assignment
was saved by the agent. Updated controls remain subject to existing edit/review gates.

### What remains before completing step1

Core DR operational workflows are implemented and representative imports, overlaps,
manual income/expenses, daily comparison and check/correction workflows are accepted.
There is no new large operational feature planned. Completion still requires:

1. Full-period acceptance: finish relevant classifications/coverage and compare a
   complete month with the source document; resolve legitimate bank20 decisions.
2. Remaining edge-case/access acceptance: representative refund/internal movements,
   cancellations/recovery where suitable examples exist, and real partner profiles.
   Automated tests cover these paths; representative client acceptance is separate.
3. Production cutover rehearsal and setup: choose historical cutoff and actual company,
   studio/account/terminal mappings, identify QA/test entries, verify backup/restore
   and repeat-upload preservation in a separate dataset.
4. Authorized release: compatible backend/frontend/migrations, health/access checks
   and first production cycle. Merge/push/deploy is not authorized by routine testing.

This is a release-validation stage, not an accurate percentage or fixed-duration
estimate. The remaining effort depends on unresolved source/classification decisions
and production setup, rather than building Spain or financial analytics.
