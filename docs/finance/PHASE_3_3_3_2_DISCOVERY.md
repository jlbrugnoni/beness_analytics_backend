# Phase 3.3.3.2 — shared payment records and routine imports

Date: 2026-10-25. Payment workbook preview (3.3.3.1) accepted by client.
This document specifies the next subphase; it does not claim payment posting exists.

## Client clarification

Historical migration is an occasional setup/recovery workflow, normally performed
once. Afterwards the client maintains the same financial history by uploading
regular source reports. Do not make the enriched workbook a recurring requirement,
or develop parallel migration-specific financial records or matching behavior.
Keep this setup section bounded; prioritize the shared receipt/import structure.

## Two entry points, one set of financial records

| Entry point | Purpose | Target |
| --- | --- | --- |
| Initial historical migration | Read the enriched workbook, preserve prior classifications, dates, payment splits and manual decisions; resolve source/account provenance | Shared bank movements, invoices/items, receipts and allocations |
| Routine report imports | Read original bank, invoice/items and payment exports, including overlaps and later status/source changes | The same shared bank movements, invoices/items, receipts and allocations |

Both retain separate immutable source batches/rows and audit history. Source format
and filename identify evidence, not a second financial ledger. A migrated payment
must be recognizable on later native imports through the same verified source
identity. One invoice still represents one sale; payment rows explain collections,
and bank rows explain actual movements. They are not three additive revenues.

A migration completion marker describes reviewed setup coverage, not a rule to
ignore older records. Reports may overlap before/after that marker or contain
payments against older invoices. No automatic deletion, reopening/closing policy,
cutover date or recurring enriched-workbook upload is inferred from this request.

## Shared structure to implement

- Generic payment import batch/row evidence with source format/parser version,
  company/provider, source metadata, actor/time and immutable original values.
  Routine upload entry must not require visiting Historical migration previews.
- Shared receipt record holds verified source identity, date, currency, amount,
  original method and current/manual assignments, regardless of entry point.
  Do not use an import row's position or a derived NCF cache as payment identity.
- Separate invoice allocations represent payments against invoices; several
  receipts can pay one invoice. If one receipt can pay several invoices, source
  allocation amounts and row grouping must be verified before confirming links.
  Preserve the whole receipt once, not once per allocation. Unsupported shape
  remains staged for review rather than inventing allocation amounts.
- Invoice links provide studio attribution using existing company/source/full
  invoice identity and permissions. Missing invoice stays pending; no placeholder
  sale or guessed studio is created to satisfy upload order.
- Original cash/account/method evidence and explicit migrated manual decisions
  remain separate. Later raw source blanks/defaults cannot erase manual work.
  Changed source facts need auditable review; upload time is not proof of truth.
- Both entry points use common matching, stale-plan/concurrency, manual review,
  provenance and dependent-undo services. Initial migration is not a shortcut around
  these controls, nor an additional daily workflow.

## Q-016 — payment identity and receipt cardinality

Asked as one numbered client question on 2026-10-25; answers pending:

1. Is Alegra's payment Numero permanent across repeated downloads and unique
   across all accounts within the same company?
2. Can one payment receipt cover several invoices, or does a receipt always
   refer to one invoice?

Evidence so far: 1,127 populated distinct payment numbers in the saved workbook,
one missing number; each dated source row contains one invoice reference. This
sample does not establish global identity/reuse or multi-invoice receipt semantics.
Do not invent a year/account namespace or assume that repeated IDs are duplicates
until the identity contract is defined. No new permission/approval is being sought;
these are missing business/source facts needed before financial posting.
Native standalone export format remains a separate parser-validation dependency,
not a reason to request the already-uploaded historical workbook again.

## Acceptance cases for the shared import service

1. Historical payment with valid source identity is migrated; the same receipt
   appears in a later native export. Reuse one receipt with two evidence links,
   preserving the migrated method/studio/date corrections; never duplicate it.
2. Native payment arrives first, then overlapping migration. Reuse that receipt;
   proposed historical manual assignments are reviewed if they conflict. Preserve
   the same financial count for either arrival order.
3. One invoice is paid by card and cash. Retain one sale, two receipts and the
   source allocation amounts. Never create a full extra payment from Cobrada or
   the invoice's default method.
4. Changed date/amount/invoice evidence is reviewed while independent valid
   records continue. Missing source rows do not delete financial history.
5. A source payment has no verified identity or invoice reference. Retain evidence
   and an actionable issue; don't fabricate a stable key or silently match by
   name/date/amount.
6. If multi-invoice receipts exist, preserve one receipt and multiple allocations;
   invoice/item row multiplication must not inflate receipt totals.
7. Refunds, cancellations and undo preserve dependent allocations and audit
   history; no dangling confirmed links or second refund/profit adjustment.
8. Finance/company/studio/sensitive permissions and stale-plan/concurrent-import
   safeguards apply equally to migration and routine report upload paths.

## Delivery boundary

This checkpoint records accepted scope, the shared structure and the two remaining
identity questions. It changes no runtime models, user data or permissions.
After Q-016, implement shared receipt/allocation posting and reuse it from historical
and routine source adapters; add a routine payment-report screen once its source
contract is verified. Avoid further migration-only feature expansion unrelated to
preserving and reviewing the initial financial history.


## Answer and implementation checkpoint

Q-016 answered (D-068): normally stable/company-wide payment number, normally one
invoice per payment. Guard exceptions. PHASE_3_3_3_2_DELIVERY.md supersedes the
planning-only runtime statements above: shared receipt processing and a strict
CSV column preset now exist; actual standalone export acceptance remains pending.
