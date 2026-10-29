# Phase 3.3 Alegra invoice and item import discovery

Date: 2026-10-25. Phase 3.2 accepted (D-051). Q-013 answered (D-052–055); exact cancellation label pending.
Phase 3.3.1 previews are implemented; financial sales posting is not. See
PHASE_3_3_1_DELIVERY.md. No production release.

## Scope and settled rules

- Add a finance-owned Dominican Alegra item-report upload, private original-file
  retention, source preview, invoice/item persistence, overlap review and audit.
  Keep existing operational imports unchanged. Spain remains on Mindbody Sales;
  its adapter belongs to Phase 5.
- Group by company/source/full invoice code; preserve every item occurrence,
  including repeated identical items. Count invoice totals once. Do not use
  customer names as identity. Confirm numbering-series evidence before finalizing
  collision handling; missing identifiers are review/invalid evidence, not guesses.
- Invoice creation normally means payment on the invoice date (D-002). All invoices
  and their items are exported for the selected period (D-044). A later report's
  absence never deletes or cancels a previously imported invoice.
- Cost center assigns studio. A conflicting studio price list warns; General is
  neutral. Unknown cost centers require review rather than price-list fallback.
- Preserve original source labels and manual decisions. Debit card means Link;
  credit card defaults to Cierre with recurring review; cash and transfer retain
  their accepted mappings. No new payment convention is assumed.
- V1 results are tax inclusive. Keep explicit source tax evidence; do not infer
  missing expense taxes or introduce net-of-tax reporting here.
- The previous sample has no exported item identifier. Full-invoice comparison
  must preserve multiplicity and validate completeness/totals before proposing a
  replacement. Report order must not become item identity.

## Q-013: questions sent

1. Can an invoice number ever be reused in another year or numbering series, or is the full number unique within the company? If you use several series, does the exported number include the prefix?
2. When a later export changes an existing invoice's date, amount or items, should the app keep the current invoice and ask you to approve the complete updated version? I recommend this, preserving its previous version and manual assignments, and flagging assignments affected by changed items.
3. Can one invoice be paid using two methods, such as part cash and part card? If yes, does your Alegra export show the amounts for each method, or do you record that split elsewhere?
4. When an invoice is cancelled or refunded, does it remain in this export with a status, disappear, or appear in a separate credit-note report? If you do not know, we can leave those cases for review until we have an example; a missing invoice will never be treated automatically as cancelled.

## Proposed delivery and verification

After answers, implement a bounded first delivery with preview, retained source
history and visible validation issues, followed by invoice posting/review with
atomic stale checks. Confirm the exact subdivision at implementation start.
Independent valid invoices may proceed; incomplete or internally inconsistent
invoices must not be posted partially or silently balanced using tolerance.

Test single/multiple/repeated items, invoice totals counted once, reordered and
identical retries, overlapping periods, changed invoice snapshots, missing rows,
numbering collisions, studio conflicts and manual assignment preservation.
Scope and privacy must cover previews, items, originals, exports and histories.
Do not copy real report/customer data into Git. Use synthetic fixtures for tests.

Cancellation/credit-note layouts are not inferred from ordinary invoices. If
unknown, document the limitation and keep unsupported evidence for review; the
accepted original-sale-month refund rule remains unchanged (BR-038).

The initial discovery checkpoint was documentation only. Phase 3.3.1 source
previews are now implemented; see PHASE_3_3_1_DELIVERY.md for validation and client
tests. Financial posting remains future work. Existing bank QA data is retained.


### Q-013 answers received — 2026-10-25

1. Full invoice codes should not repeat within either company. Dominican series
   begin B01/B02 followed by eight digits. Keep company/source/full code identity,
   including prefix, rather than year-based reuse (D-052).
2. Yes to approval of changed source evidence, but Alegra currently allows only
   cancellation, not edits to invoice date, amount or client. Treat such changes
   as anomalies, retain the original and require investigation rather than offering
   ordinary edits to those values. Cancellation/status approval remains a later
   posting workflow (D-053).
3. No mixed payment methods in the current workflow. One or two cards can fund one
   invoice at the same moment; bank settlement is the whole day's card deposit.
   Do not require a split per card or assume card count changes invoice totals
   (D-054). Partial/grouped settlement matching remains Phase 5.
4. Cancelled invoices remain in the export with a cancellation status. The refund
   happens later as a bank debit. Preserve both events, remove the sale's result
   contribution in its original month and do not deduct the same refund twice
   (D-055, BR-038). Exact cancellation text in ESTADO is still pending: the sample
   contains only Cobrada. A focused asynchronous question requests that text.

First delivery: Phase 3.3.1 source previews. Invoice posting, approval of changed
statuses and refund reconciliation follow after preview review. This subdivision
keeps unconfirmed cancellation labels from being guessed.
