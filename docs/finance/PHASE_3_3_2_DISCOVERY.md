# Phase 3.3.2 sales posting, overlap and cancellation review

Date: 2026-10-25. Phase 3.3.1 source previews accepted (D-056).
Q-014 answered (D-057–058). Phase 3.3.2 implemented and validated; client
acceptance pending. See PHASE_3_3_2_DELIVERY.md for delivered behavior and limits.

## Scope and accepted boundaries

- Add a finance sales ledger for Dominican Alegra, retaining full invoice code,
  all item occurrences, source support, actor/history and separate assignments.
  Spain remains on existing Mindbody Sales; no source cutover is introduced.
- Previewed source batches remain immutable. A sales posting is a separate action;
  saving an upload is not financial posting. Existing user-uploaded QA files and
  bank movements must not be modified during developer tests.
- Identity is company/source/full invoice code (D-052). Reordered rows and repeated
  identical items must compare by complete item multiplicity, not row position.
  Count each invoice total once; missing invoices never cancel current sales.
- Commit independent complete valid invoices. Invalid/incomplete invoices and
  uncertain statuses remain review work. Do not partially post invoice items or
  use tolerance to conceal invoice-total differences.
- Date, amount and client are immutable under the present Alegra workflow
  (D-053). Unexpected changed facts are anomalies for investigation, not ordinary
  editable values. Current posted facts stay intact while pending review. Old
  source files cannot silently restore a previously cancelled invoice.
- Known cancellation status changes require explicit approval before changing
  posted sales. Keep sale facts and source versions for the original sale period
  (BR-038/060). A later bank refund is settlement of that cancellation and must
  not cause a second result deduction. No bank refund is fabricated from status.
- Cost center is the primary studio mapping; price list conflicts warn and General
  is neutral. Map debit card to Link, credit card to Cierre with recurring review,
  cash to cash, transfer to transfer. Preserve manual invoice assignments across
  new source observations. Changes to defaults do not silently restate them.
- Use the existing permission approach: source privacy/company scope protects all
  actions; financial import requires import capability and assignment/review
  changes require edit capability. Reuse own-posting/settings-manager undo
  authority with protected-record safeguards (D-046/049), without asking again.

## Q-014: questions sent

1. What exact text appears in Alegra's ESTADO column for a cancelled invoice? The supplied sample contains only Cobrada; we still need the cancelled label rather than guessing it.
2. Do you sometimes cancel an invoice and issue a replacement without returning money to the client, or does every cancellation require a refund? For example, correcting an invoice could leave the original payment in place. This determines whether a cancellation should show a refund pending or a replacement/no-refund explanation.

Question 1 carries forward the unanswered exact-label request from Q-013; it does
not reopen cancellation's accepted original-period financial treatment. Question
2 distinguishes bank-refund settlement from cancellation itself. Neither an
unanswered question nor a synthetic Anulada test row confirms a source alias.

## Implementation approach after answers

1. Add ledger/posting/decision/history records and company-level stale-plan guards.
   Preserve original previews and record versioned posting interpretation. Old
   preview summaries must not be silently rewritten when a status alias is added.
2. Show new, unchanged, pending source change, invalid and unknown-status counts.
   Resolve company/code identity without duplicating sales across overlapping
   reports. Persist exact source occurrence support and item snapshots.
3. Provide explicit commit and status-review confirmations, source comparison,
   mapped studio/channel evidence, manual recurring/studio correction and audit.
   Newly encountered cancelled invoices retain evidence with no paid contribution;
   later cancellation of a posted paid invoice requires the accepted approval.
4. Add audited undo for eligible untouched creations. Preserve pre-existing linked
   invoices, approved status changes, manual work and reconciled/dependent records.
   Reuse stale checks and reversal safeguards rather than deleting source history.
5. Deliver focused test instructions before advancing. Expense classification,
   historical migration, refund-to-bank matching and final result calculation
   remain later phases. Do not claim cancellation matching or results are complete
   merely because invoice status is stored.

## Verification plan

- Multiple and repeated identical items, shuffled order, retries and overlapping
  periods count an invoice once. Distinct full codes and company scopes stay apart.
- Changed date/amount/client stays unresolved and cannot silently replace facts.
- Cancellation review preserves original facts/period and source history; missing
  invoices and stale paid files cannot reverse it automatically. Unknown statuses
  stay pending. Use confirmed cancellation labels in synthetic tests only.
- Manual studio/recurring assignments survive source repeats and rule edits;
  conflicts remain visible. No full-company source exposure to studio-only users.
- Concurrent commit/review/undo and stale config plans cannot duplicate invoices
  or overwrite intervening decisions. All sensitive paths recheck access.
- Undo only eligible new records; protect prior support, manual/reconciled changes
  and approved status decisions. No application test is due at this discovery step.


## Q-014 answers received — 2026-10-25

1. ESTADO uses **Anulada** (D-057). Recognize Cobrada as paid and Anulada as
   cancelled, with normalization for case/whitespace. Do not guess other statuses.
2. Yes, invoices may be cancelled/reissued without refunding the client (D-058).
   Cancellation alone does not prove a refund is owed or paid. Keep settlement
   pending until an operator records refund expected, no refund, or a replacement
   invoice in the same company. A note is required. Do not create a bank movement
   or second profit deduction from that choice. Original-period treatment remains
   BR-038; refund-to-bank matching remains Phase 5.
