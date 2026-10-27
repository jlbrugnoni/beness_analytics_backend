# September 1–15 replay audit — 2026-10-27

Client requested a read-only check of overlapping imports and preserved classifications.
No import decisions, sources, classifications, flags or financial records were changed.
Audit used a consistent read-only SQLite copy of the current persistent local database.
Private evidence/snapshot: .local-backups/overlap-audit-20261027T151739Z/ (outside Git).

## Scope and result

Only the September bank CSV is present as a new routine report in the local database:
bank batch20, account1 (Popular operating), company1 (QA financial company), posted
2026-10-27 at11:13:27 America/Santo_Domingo. It contains175 valid movements dated
September1–15:100 credits and75 debits. Historical bank batch19 comes from workbook8.

| Decision | Rows | Actual effect |
| --- | ---: | --- |
| Created | 161 | New September2–15 bank movements |
| Linked | 4 | Reused existing September1 credits; no duplicate movement |
| Pending | 10 | Existing September1 overlap candidates held for review; no new movement or overwrite |
| Total | 175 | Every source row accounted for |

The14 September1 report occurrences match the14 historical bank occurrences by date,
direction, currency and amount, including two distinct6,800.00 credits. No September1
movement was newly created. The entire September1–15 ledger has175 active movements,
with exactly the same date/direction/currency/amount occurrence multiset as the report.
Credit total2,637,891.36DOP and debit total2,491,914.56DOP match the bank report exactly.
No duplicate or missing amount/date occurrence was found for this report's period.
This checks import integrity; it is not bank-to-sales reconciliation or source-coverage
certification beyond the supplied report.

## Classification preservation

Compared all322 original historical movements with their latest audit snapshots from
before batch20 began. All322 have baseline evidence. There are:

- Zero changed classifications and zero changed original source snapshots.
- Four subsequent historical-record events, all link events from this import; no
  classify/correct/delete/undo events changed a historical record during/after it.
- Preserved nonempty assignments include145 categories,144 subcategories,151 expense
  periods,171 operation dates,171 payment methods,272 studios,121 terminals,
  322 manual descriptions and145 true reviewed flags. Empty assignments also remain
  empty; an unchanged incomplete classification is not certified as complete.

## Matching issues exposed by real data

Safety/preservation checks pass. Automatic overlap recognition is only partial and
needs improvement before describing this replay as fully automatic.

At commit, the10 pending decisions were labelled8 correction /2 ambiguous. On a fresh
plan after posting,9 show ambiguous /1 correction because newly imported later dates
add weak candidates through reused terminal/serial references. These are still the
same10 pending decisions; a changed plan label is not another import or a lost record.

| CSV source line | Direction | Amount DOP | Historical candidate | Evidence / issue |
| ---: | --- | ---: | ---: | --- |
| 13 | Credit | 42,498.60 | 672 | Same date/amount/balance; AZUL description differs only in whitespace |
| 14 | Credit | 9,880.00 | 673 | Same date/amount/balance; AZUL description differs only in whitespace |
| 15 | Credit | 36,805.10 | 674 | Same date/amount/balance; AZUL description differs only in whitespace |
| 16 | Credit | 6,460.00 | 675 | Same date/amount/balance; AZUL description differs only in whitespace |
| 17 | Credit | 52,592.00 | 676 | Same date/amount/balance; AZUL description differs only in whitespace |
| 18 | Credit | 77,045.60 | 677 | Same date/amount/balance; AZUL description differs only in whitespace |
| 20 | Credit | 6,800.00 | 679 | Same date/amount/balance; other6,800 occurrence has a different balance |
| 22 | Credit | 6,800.00 | 681 | Same date/amount/balance and compatible description; other6,800 occurrence has a different balance |
| 115 | Debit | -20,000.00 | 510 | Date/amount match; raw bank description matches workbook manual description, not its original-description field; bank adds balance/serial |
| 116 | Debit | -75.00 | 511 | Date/amount match; raw bank description matches workbook manual description, not its original-description field; bank adds balance |

Candidate IDs above are audit evidence, not approved identity decisions. All eight pending credits have a unique matching same-day amount/balance candidate
whose description matches after whitespace normalization. Seven differ in their raw
description spacing; line22 already has an exact description match. These facts were
verified without normalizing stored evidence or resolving any decisions. Same amount/date alone is insufficient
authority to link or create a record, especially when two equal credits exist.

Recommended next implementation: normalize insignificant description whitespace for
comparison without changing raw evidence; prefer unique compatible date/amount/balance
evidence over weak reused-terminal candidates, preserving genuine equal occurrences;
keep substantive description/identity conflicts reviewable. The debit description
differences require explicit identity review; do not rewrite bank facts/classifications
or auto-resolve pending decisions merely because totals match. No code fix is included
in this audit-only delivery.

## Alegra scope still outstanding

No routine September invoice or payment uploads are present in any company in this
local database. Company1 currently has historical sales batch9 (744 invoices) and
historical payment batch9 (745 receipts plus one invalid payment decision). There were
no sale/receipt events since the September bank import. Therefore September Alegra
overlap, item matching, split-payment preservation and invoice/payment source-change
handling cannot yet be certified against the requested new reports. Ask the client
to upload those two September reports through the routine upload selector.

Overall: bank amount/date integrity and historical preservation pass;10 overlaps remain
pending, matching UX/normalization needs refinement, and new Alegra replay is untested.
