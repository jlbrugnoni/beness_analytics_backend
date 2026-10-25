# Phase 3.3.3.2 — shared receipts and payment import processing

Date: 2026-10-25. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. No push/merge/deployment.

## What I did

Q-016 answered: client says payment Numero normally remains stable/company-wide
unique and, as far as known, one payment refers to one invoice (D-068). Treat
this as the normal guarded identity, not proof that every source is error-free.

- Added migration 0011: shared PaymentImportBatch/Row, PaymentPosting,
  FinancialReceipt, PaymentDecision/Event and company payment revision. Financial
  receipts use unique active (company, provider, number) identity. Source snapshots
  and current assignments are separate. One nullable invoice link represents the
  full positive receipt amount against one invoice in v1; several receipts can
  pay one invoice. Multi-invoice source references stay invalid/reviewable.
- Added /finance/payment-imports as the recurring entry point, linked from Finance.
  Historical migration is under Initial setup and historical migration. Both
  entry points use the same receipt/import/link/review/undo services and ledger.
- Added strict payment CSV preset using the columns observed in Alegra_adm:
  Fecha, Numero, Valor, Asociaciones, Tipo_nota, Metodo_pago. Optional corrected
  methods/studios and other source columns are retained. UTF-8 BOM/Windows-1252;
  exactly one recognized semicolon/comma/tab header shape. Unknown layouts,
  malformed widths and unsupported data fail closed, retaining source evidence.
  This preset is tested against synthetic CSVs matching the observed columns;
  an actual standalone native Alegra export has NOT yet been verified. Do not
  claim support for arbitrary Alegra report names/layouts. Adjust the adapter
  after the first native export if its header contract differs; don't request
  the already-uploaded historical workbook again.
- Existing workbook payment preview can Prepare shared payment import, preserving
  selected month or all-date scope and immutable normalized source rows. This is
  preparation only; explicit Import valid payments confirmation posts receipts.
  Invoice/review search filters do not constrain the prepared date scope, as the
  UI explicitly explains. Original XLSX bytes stay referenced in MigrationImportBatch;
  originals are not rewritten or duplicated into a new workbook.
- GET processing plans separate new/reused/conflicting/invalid rows; commit creates
  independent valid receipts, reuses unchanged identities and holds conflicts.
  No file-name/row-position/invoice-code unique receipt key, silent source update,
  source-row deletion or fabricated missing external number. A failed/empty source
  cannot post. Repeated commit is idempotent; after undo a fresh source is required.
- Source facts (number, date, amount, currency, invoice reference, kind, original
  method/account/customer evidence) are compared across origins. Later raw blanks
  for corrected method/studio cannot erase migrated manual work. Incoming enriched
  assignments against different existing evidence remain pending, with explicit
  Keep current payment + reason available. Source replacement approval and manual
  completion of missing source identities remain later review work.
- Preserve manual Cierre/Link/Recurrente/cash/transfer assignments; otherwise use
  existing company payment-method mappings, keeping their review flags (credit
  card defaults may need recurring correction). Preserve historical studio labels;
  exact same-site studio matches can be assigned, unknown labels remain pending.
  Without a manual label, studio attribution follows the linked invoice. No bank
  or cash balance/account movement is created from a receipt.
- Exact company/provider/invoice-code linking is attempted after receipt posting
  and after invoice posting/cancellation review. Missing invoices leave receipts
  waiting, so either arrival order is supported. Only eligible paid invoices with
  sufficient unallocated amount are linked automatically; overpayments or explicit customer-name conflicts remain
  unlinked for review. Existing allocations take priority. Cancelled linked invoices
  retain receipt provenance with a visible cancellation issue. Existing source
  invoice/customer/amount differences are NOT silently reconciled by this step.
- Sales undo protects invoices with active receipt links. Receipt undo reverses
  only untouched creations, preserves reused/edited/reconciled/other-supported
  receipts, records reasons and supports retry/partial undo. Automatic links alone
  do not falsely classify a receipt as manually edited. Undo does not delete source
  evidence. Ownership/manager rules match existing imports.
- Editable receipt payment method with expected revision and required reason,
  protected against reconciled edits. Reuploads preserve manual changes. Source
  evidence shows incoming versus original stored evidence and current assigned
  method separately. Both receipt and posting histories are audited.
- New /api/finance/payment-imports/ upload/history/detail, companies/, from-migration/,
  processing/, commit/, source-row/, retain/, undo-preview/, undo/, original/;
  /receipts/ list/detail/history/options/assign. Source/account/sensitive/company-wide
  privacy reuses migration permissions. Upload/post requires import, edit/retain
  requires relevant edit access, undo requires ownership/manager and import/edit.
  All responses private/no-store; cross-company/studio-only paths are inaccessible.
- Company-wide locks, shared payment/sales/config/mapping revision tokens and a
  unique active receipt constraint prevent stale/parallel uploads from duplicating
  receipts or overallocating invoices. Company site/currency cannot change after
  payment source history. Explicit non-DOP currency or unrecognized payment status
  stays for review; DR context supplies DOP when the observed export has no currency.

## Validation

- PostgreSQL 16: 299 supported tests passed (218 finance + 81 existing analytics,
  purchase matching/repair and import-guard tests). Eighteen new CSV/receipt tests,
  including two actual concurrent receipt-import tests. Final focused 18-test PG
  run also checks the database uniqueness assertion.
- Final focused SQLite: 28 payment reader/posting tests discovered, 26 passed and
  the two new PG-only races skipped. Earlier supported SQLite regression run also
  passed before final added cases. Legacy core_data.tests removed-Center discovery
  issue remains unrelated/outside the supported targeted suite.
- Frontend lint and production build passed with pre-existing unrelated warnings;
  Django system and migration consistency checks passed. Migration 0011 applied
  only to isolated QA/test databases, never the normal or production database.
- Browser synthetic company Receipt posting synthetic QA (company #6), source #5,
  shared import #1: two receipts (100 Cierre + 200 cash) created, both linked to
  one synthetic 300 invoice; missing-number 95 row held. Source evidence verified;
  manual recurring edit preserved; undo preview shows one protected edited receipt
  and one eligible receipt (no browser undo executed).
- Browser Finance navigation confirmed routine Payment imports and collapsed
  initial migration section. Re-preparing the same synthetic source through that
  section creates shared import #2: two existing payments + one invalid row, zero
  new payment identities. Manual Recurring remains intact. Import #2 is still a
  source plan, not committed in browser QA.
- Screenshot /private/tmp/finance-shared-payments/receipts.png contains synthetic
  data only. Logs in /private/tmp/finance-shared-payments/{pg-final,pg-focused-final,
  sqlite-final-focused,lint-final,build-final}.log.
- Real workbook previews #2/#3 hashes unchanged; no shared import was prepared
  from them by the agent; real-workbook company #5 has zero FinancialReceipt rows.
  All seeded/posted invoice and receipt test data is in separate synthetic company
  #6 on the isolated local QA database. No user grants changed; no external review.

## What you should test

Open http://127.0.0.1:3037/finance/payment-imports with the existing QA login.
Choose Receipt posting synthetic QA for this first financial-processing test.

1. Open shared import #2. Expect two Existing payment rows and one Invalid source
   (missing payment number), with two active receipts below. Import valid payments
   should reuse them, not add receipts; the missing-number row stays held.
2. Confirm invoice B0200009001 has two receipts (100 and 200), and the 100 receipt
   retains its manually corrected Recurrente channel. Inspect Source evidence:
   original Cierre and current assigned method remain distinguishable.
3. Edit a payment method with a reason; refresh/re-prepare should retain it.
4. Shared import #1 → Preview undo must protect edited receipts and any receipts
   now supported by committed import #2. Undo is a real QA-data action; review
   eligible/protected counts before confirming.
5. Finance → Initial setup and historical migration → synthetic source #5 →
   Show Alegra payments → Prepare shared payment import should route to the same
   Payment imports screen. No financial records are created until confirmation.
6. Real preview #3 remains available, unchanged. Full historical financial
   migration is not certified by these synthetic receipt tests.

## Remaining scope

Historical expense/category/account provenance and cash/manual migration decisions,
completed real September comparison, raw native Alegra export acceptance, approving
source-fact replacements/missing payment identities, partial/outstanding invoice
status/result semantics, refunds/settlements, and Spain adapters remain later work.
This step does not produce monthly profit, bank reconciliations, validated cash
balances, or a completed historical cutover.
