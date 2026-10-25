# Phase 3.2 bank transaction commit, overlaps and undo discovery

Date: 2026-10-24. Phase 3.1 accepted (D-048). Q-012 sent; answers pending.
This document is a proposed delivery design, not implemented financial posting.

## Existing accepted boundaries

- Retain original bank preview/source evidence; do not rewrite or hard-delete it
  when committing or undoing financial effects. Preview history is already live.
- Popular daily/overlapping and Caixa periodic files are normal. Missing rows
  in a partial upload do not delete or cancel earlier movements.
- Identical source occurrences may be genuine repeated movements. No global
  date/description/amount natural key may collapse them or block the file.
- Manual assignments survive retries/source changes. Ambiguous identities require
  review; independent valid new rows can proceed. Invalid amounts/dates do not
  generate placeholder movements.
- Audited undo covers untouched records created by that upload; later manual
  edits or reconciliations require review. Existing records encountered again
  remain. D-046 did not specify authority over another user's upload.
- Full bank-account/sensitive-detail scope continues to protect unclassified
  bank detail. Import and edit capabilities remain distinct actions.

## Q-012: questions sent

1. Who may undo another user's import? Recommend operators undo their own;
   users with Manage financial configuration can undo others' imports too.
   Relevant import/edit permissions and full account access remain required;
   edited/reconciled record safeguards apply to everyone.
2. If a later bank report appears to correct an existing transaction's amount
   or date, should replacement require review? Recommend preserving the existing
   transaction and displaying the proposed correction for approval, while
   independent valid new rows can still import.

## Proposed technical sequence

1. **Commit plan.** Compare immutable valid preview rows with the current
   account ledger and expose new/unchanged/proposed-change/ambiguous/invalid
   outcomes. Keep source occurrence evidence, candidate links and reasons.
   Failed file-wide parses cannot be committed. Plan versions must detect ledger
   changes rather than silently apply an outdated preview.
2. **Atomic financial posting.** Recheck permissions, account/company state and
   plan versions under account/company locking. Persist financial movements
   separately from raw rows. Preserve signed bank amounts/dates/reported balances
   without inventing classifications, operation dates or expense periods.
   Invalid/ambiguous rows remain pending while independent valid rows post.
3. **Overlap decisions.** Exact same-file retries can reuse prior source
   occurrence links. Different files need occurrence-aware evidence and review
   when identity is not reliable. References are supporting evidence, never
   globally unique identifiers. Link rows to existing movements or create a
   distinct occurrence through explicit resolution; preserve actor/history.
4. **Correction review.** Preserve prior source versions/manual fields. Use the
   client-selected Q-012 policy before adopting changed amount/date evidence;
   do not silently replace an existing transaction or interpret absence as a
   deletion. Future results/reconciliation dependencies must remain traceable.
5. **Undo preview and execution.** Show records eligible for reversal and those
   protected by manual/source changes, reconciliation or other active import
   dependencies. Another active upload's evidence is not discarded by undoing
   the first upload. Reverse eligible financial effects with audit/history;
   leave raw files, prior events and reused existing records intact. Final
   authority checks depend on Q-012. No force-undo shortcut for managers.

These are implementation responsibilities within the accepted scope, not requests
for client approval of model names or database design. Keep raw source evidence
separate from mutable processing/execution status; the existing preview APIs
must continue to represent what was uploaded at that time.

## Validation plan

- Popular/Caixa parsing controls remain unchanged; source rows are not newly
  reinterpreted during posting without a versioned preview.
- Identical retries/reordered files/overlapping date windows do not create extra
  movements; genuine repeated occurrences remain separate. Ambiguous rows do
  not block independent valid new rows. Do not overclaim automatic matching.
- Concurrent commits or stale plans cannot double-create movements.
- Source date/amount corrections follow Q-012 and preserve manual fields/history.
- Undo leaves reused records and dependent/edited/reconciled movements protected;
  repeated undo is safe and cannot delete another upload's retained evidence.
- API action and account/privacy scopes are tested on every path, including
  histories, review candidates and source-file access.
- Existing analytics/import regression tests and EN/ES browser checks continue.

## Delivery boundaries

No expense-classification screen, cash/manual-entry workflow, terminal-date
inference, monthly result, allocation or sales reconciliation is claimed by this
bank-posting step. Alegra invoice imports and enriched historical migration remain
later Phase 3 deliveries. Completed-month DR pilot approach is accepted, but the
exact pilot month/cutoff is still selected during migration preparation.

No code, migrations, reports, financial records or grants changed in this discovery
checkpoint. Both repositories remain on feature/finance-phase-2; no production
push, merge or deployment authorized.
