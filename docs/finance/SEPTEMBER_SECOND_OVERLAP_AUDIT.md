# September 14–30 Popular report: false identity candidates

Read-only investigation, 2026-10-27 local date. No financial records, import
decisions, classifications, checks or permissions changed.

## Source and saved posting

Bank batch21: `Banco Popular Dominicano 14 al 30 sept Deb. y Credit.csv`.
Posting13 is active. Parser summary:170 valid rows,0 invalid,0 repeated occurrences;
81 credits totaling973,877.56DOP and89 debits totaling1,526,383.72DOP.

| Saved result | Credits | Debits | Total |
| --- | ---: | ---: | ---: |
| Linked to existing ledger movement | 18 | 35 | 53 |
| Created new movement | 13 | 19 | 32 |
| Pending identity review | 50 | 35 | 85 |

All53 linked rows are on September14/15 (15 rows on14th,38 on15th).
All85 pending rows are on September16–30; every returned candidate is on a
different bank date. Pending credits total628,785.03DOP, pending debits710,296.92DOP.
Pending means the rows are held outside the ledger, not posted duplicate money.

## Confirmed matching defect

`bank_posting.plan` indexes both reference and serial as independent identifiers,
without requiring compatible transaction facts for this fallback. Its v3 strong
same-day/balance preference fixes some historical overlap candidates but does not
prevent a new row from becoming ambiguous solely because of a recurring serial.

All50 pending credits have serial collisions and no nonempty reference collision:
44 are AZUL settlements and6 are other incoming transfers. The serial identifies a
terminal or recurring party, rather than an individual transaction.

Example: source line30, September16,9,514.90DOP, reference259018570,
serial0039618800006. Its11 suggested candidates include September2,
69,267.70DOP, reference245019213 with the same serial. Dates, amounts, balances and
references differ. A shared terminal must not by itself make these transactions
duplicates or corrections.

Of35 pending debits,24 have both reference and serial collisions,9 serial alone,
and2 reference alone. All26 nonempty reference collisions use the generic value`1`.
Such generic references also cannot establish transaction identity across days.

## UI finding

The daily upload page shows pending status and a source-information button, but no
row-level resolution action. Its advanced link opens `/finance/imports?batch=21`.
The BankPostingPanel on that older page has Review dialogs with Create new,
Link, Correct and Ignore, gated by import/edit permission. This route is too hidden
for a normal pending-review workflow. Candidate-first defaults also encourage linking
when the candidates themselves arose from weak identifiers.

## Recommended next implementation

1. Give Popular provider-specific identity rules: serial/terminal/party reuse alone
   is insufficient. Generic references such as`1` are weak evidence. Retain exact
   overlap recognition and review of real conflicts or indistinguishable occurrences.
2. Add regressions for recurring terminals, recurring transfers and generic debit
   references across days, plus same-day distinct occurrences and genuine overlaps.
3. Re-evaluate pending rows under the corrected rules in a disposable copy. Preserve
   all53 links,32 creations, previous classifications and saved manual decisions.
   An already active posting's commit is idempotent, so simply pressing Import again
   will not resolve its pending decisions. Recovery needs an explicit audited path.
4. Put a clear Review pending action in the daily upload workflow. Do not require
   the client to manually resolve85 rows caused by this defect.

This investigation does not change matching code or resolve the saved85 rows.

Follow-up: D-088 is implemented and tested in BANK_MATCHING_V4_DELIVERY.md. The
working pending rows remain for client confirmation through the new daily review UI.
