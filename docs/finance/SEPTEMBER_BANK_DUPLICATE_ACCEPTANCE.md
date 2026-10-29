# September bank import: post-recovery duplicate audit

2026-10-28, following client acceptance of D-088 recovery and repeat upload.
Read-only audit against a consistent SQLite backup opened in read-only mode.
Private evidence: `.local-backups/bank-duplicate-audit-20261028T134704Z/`
under the workspace root (database.sqlite3 and audit.json, not committed).

## Confirmed result

- Report21:170 rows map to170 distinct active movements, with53 existing overlap
  links and117 creations. No pending decisions remain.
- All53 overlap links point to report20's existing movements:15 on September14,
  38 on September15. No overlapping movement was recreated.
- All117 creations belong to September16–30; no September14/15 creations.
- Repeat report22:170 links to exactly the same row-to-movement mapping as report21,
  with0 creations and0 pending decisions. Original file hashes are identical.
- Reparsed immutable original CSVs match all saved source rows; source hashes verify.
- All170 linked ledger sources match original bank date, signed amount, normalized
  description and balance (with account/currency/direction scope).
- Selected unique ledger totals equal the report: income973,877.56DOP,
  expenses1,526,383.72DOP. No four-fact ledger duplicate group includes any of
  report21's created movements.

## Repeated-looking entries

September29 includes equal-value expenses sharing descriptions. They have distinct
reported balances and distinct source occurrences; these were correctly retained as
separate transactions. Repeated dates/amounts/descriptions alone are insufficient
grounds for deletion.

The broader active-ledger scan found six preexisting August groups with equal
date/amount/generic description and missing balances, all from historical workbook19.
Five groups are distinguishable by detailed concepts/references. One group of four
payroll rows has identical available details and no balance/reference/payee identity;
it needs client/source confirmation if investigating historical duplication. These
four rows already existed in distinct workbook rows and were not created by report21
or22. Private audit evidence records IDs and workbook coordinates; do not automatically
remove legitimate equal-pay payroll occurrences.

## Scope and remaining work

No duplicate creation was found in the September recovery or repeat upload. This is
not certification of the historical payroll group or full monthly reconciliation.
Report20 retains10 pending decisions (8 recognized candidates and2 substantive
source-description conflicts). They are separate from the successful report21/22
duplicate checks. No records, decisions, classifications or permissions were changed
by this audit.
