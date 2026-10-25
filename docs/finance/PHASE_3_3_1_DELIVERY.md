# Phase 3.3.1 Alegra source preview delivery

Date: 2026-10-25. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. No push, merge or deployment.

## What I did

- Recorded Q-013 answers as D-052–055 / BR-058–060. Source cancellation text is
  still pending; sample has only Cobrada. No unconfirmed cancelled-state alias.
- Added read-only Dominican Alegra item CSV reader, version alegra-items-v1,
  UTF-8/BOM and cp1252, semicolon separator and optional separator hint/preamble.
  Limit: 5 MiB and 20,000 source records. Physical line ranges and all raw cells
  are retained, including multiline cells and repeated tax column names.
- Added migration 0008 with SalesImportBatch, SalesImportRow and
  SalesImportInvoice. These are immutable source previews, not posted sales.
  Original bytes, upload actor/time, parser version, raw rows and grouped invoice
  evidence are private. Same-file uploads create another preview linked to the
  previous one within that company/provider. No global invoice ledger yet.
- Grouped full codes including prefix; DR B01/B02 plus eight digits are validated.
  All repeated item occurrences remain. Header date/status/client/method/studio/
  price-list/total must agree across rows. Item totals must sum exactly to the
  repeated invoice total. Invalid items exclude the entire invoice from paid
  preview totals, while independent valid invoices remain visible.
- Observed SUBTOTAL - PRODUCTOS/SERVICIOS is per item in this sample, not an invoice
  header. Never require it to agree across rows. Keep tax/discount/raw evidence
  without deriving unverified tax-bearing export formulas. This DR reader only
  validates exported item totals against exported invoice totals.
- Only Cobrada counts as a known paid status. All other statuses remain visible
  for review and are excluded. A malformed/truncated file retains evidence but
  cannot report eligible invoices or a paid total. Missing invoices never cancel
  earlier ones. Source previews do not prove full-period completeness.
- Added /api/finance/sales-imports/ with company options, history/upload, detail,
  paginated invoices, review filter, raw rows/per-invoice items and protected
  original download. No PATCH, DELETE, posting, replacement or refund endpoint.
- All source paths require finance/money, sensitive detail and company site-wide
  scope; import additionally gates uploads/downloads. No bank-account grant is
  required. Studio-restricted access cannot expose an entire source file. All
  responses use private/no-store. Company site/currency cannot be reinterpreted
  after sales source history exists. Sources are not exposed in admin/media.
- Added EN/ES /finance/sales-imports linked from Finance, with upload, history,
  invoice totals/item counts, validation explanations, review filter, item/source
  detail and original download. Source labels are shown without assigning studios
  or channels yet; mapping/conflict decisions belong to the posting step.

## Validation

- PostgreSQL 16: 235 tests passed (154 finance + 81 existing analytics/purchase/
  import regressions), including 18 sales-preview tests and existing import races.
- SQLite: 235 discovered, 233 passed, 2 PostgreSQL concurrency tests skipped.
  Final focused sales tests also passed after adding customer-consistency checks.
- Django system/migration consistency checks and frontend lint/production build
  passed. Existing unrelated lint warnings remain.
- Original report parsed read-only: 456 items, 438 invoices, 438 validated paid,
  zero review invoices, DOP 2,574,587.60, September 1–15, 2026. No raw client report
  committed, copied into test fixtures or posted by the agent.
- Browser synthetic QA verified upload, 3 invoices/4 items, 1 valid paid invoice,
  2 review invoices, DOP 200.00 counted once; retained identical item occurrences;
  review filter; and readable unknown-state/incomplete-invoice warnings.
- Screenshot: /private/tmp/finance-phase3-3-sales-preview.png. Browser file chooser
  took unusually long but completed; no application defect was inferred from it.
- Only the isolated temporary SQLite QA database was migrated. Production/normal
  DB, grants, bank postings and previously user-uploaded bank reports unchanged.
  Legacy core_data.tests still references removed Center; targeted existing
  regression modules above remain the supported suite at this checkpoint.

## What you should test

Open http://127.0.0.1:3037/finance/sales-imports using the existing finance QA login.
Choose the Dominican QA company and upload the original Alegra item CSV. Expect
438 invoices, 456 item rows and paid total 2,574,587.60 DOP for the supplied sample.
Open an invoice with several items: total counts once and every item remains.
Upload the same report again: a linked preview appears without posting sales or
raising duplicate-key errors. Review invoices can be filtered separately.

Synthetic preview #1 under QA financial company is already available: two
identical items total 200.00, an unrecognized Anulada status is excluded, and an
incomplete 300.00 invoice with 100.00 of items is flagged. Anulada is synthetic
pending the exact client-confirmed cancellation label, not a source-derived alias.

## Not delivered yet

Financial sales ledger, cross-upload invoice comparison, approval of cancellations,
refund linking, studio/channel assignments and recurring overrides, undo of sales
postings, result updates and reconciliation follow in Phase 3.3.2/Phase 5.
Historical migration remains Phase 3.4; Spain remains Mindbody for Phase 5.
Do not interpret a saved preview as imported sales in management results.
