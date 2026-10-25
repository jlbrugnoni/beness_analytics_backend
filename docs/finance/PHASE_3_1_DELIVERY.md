# Phase 3.1 bank preview and history delivery

Date: 2026-10-24. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. This covers Phase 3.1 and the initial
Popular/Caixa CSV readers from 3.2, not the complete Phase 3 import pipeline.

## What I did

- Recorded Q-011 answers in D-043–046/BR-052–054: daily/overlapping Popular,
  less frequent Caixa, complete routine Alegra exports, completed-month DR pilot
  approach (exact month not selected), and audited financial undo boundaries.
- Added BankImportBatch and BankImportRow, migration
  finance.0006_bankimportbatch_bankimportrow_and_more. Batches preserve account,
  provider, original filename/bytes, SHA-256, byte size, encoding, parser version,
  actor/time, result, issues and optional earlier-identical-preview reference.
  Rows preserve every CSV record, source line range, section, original cells,
  parsed fields and issues. Duplicate-looking rows are separate occurrences.
- Original files are bounded private database bytes, not public media URLs.
  Raw preview models are not registered in Django admin. No financial movement,
  invoice, fee estimate, corrected assignment or reconciliation is created.
- Added versioned Popular comma-CSV and Caixa semicolon-CSV readers. UTF-8/BOM
  and Windows-1252 supported, quoted multiline cells retained. Popular repeated
  section headers and short debit/credit labels determine signs. Caixa retains
  signed amounts and optional EUR suffixes. Explicit bank number format is
  decimal point with optional comma thousands; other formats raise row issues.
  Dates are day/month/year. No balance-delta inference or date sorting is used.
- Added /api/finance/bank-imports/ GET/POST, detail GET, paginated /rows/
  (kind=data/invalid/all) and protected /original/. No edit/delete/commit route.
  Creation is atomic; scope and account/company state are rechecked after parsing.
  File errors stay failed previews; invalid rows remain alongside valid rows.
  Non-CSV, empty, over-5-MiB or wrong country/currency/account requests are rejected.
  Maximum 20,000 CSV records; file-wide structural errors never imply a commit.
- All reads require finance/money, full-account and sensitive-detail grants.
  Upload and original-file retrieval additionally require import capability.
  Full-account scope uses existing participating-studio/site rules; it is not
  restricted to settings managers. Preview responses are private/no-store.
  This protects unclassified salary data until transaction redaction exists.
- Added EN/ES /finance/imports page, finance landing link, supported bank-account
  selector, upload form, account-specific paginated history, summaries, issue
  filters, source-cell dialog and original download. No original file is executed
  or interpreted as HTML. Dates shown are observed coverage, not completeness.

## Important boundaries

An identical byte-for-byte reupload is a new immutable preview linked to the
prior preview for the same account/provider. This is upload history, not financial
transaction deduplication. Different overlapping files are not matched yet.
Source rows are never collapsed by a global date/description/amount hash.

Valid-row credits/debits/net are source parsing controls only. Net bank movement
is not profit or verified closing balance. Missing balance stays null. Invalid
amounts/dates cannot produce zero-valued movements. No terminal-to-operation-date
or category assignment is persisted by preview. The final DDMM in a Caixa concept
remains original text; date inference belongs to the movement/review step.

Account choice is explicit. The reader does not verify bank-account ownership
from a source account number; configured provider/country/currency is checked.
Historical enriched Excel tables and Alegra files are not accepted on this bank
CSV surface. Spain still uses existing Mindbody sales in later processing.

Audited undo (D-046), source refreshes, financial commit and conflict resolution
are next steps. Undo is not implemented as deletion of raw preview history.
Financial acceptance scenarios such as A-01 are not marked complete merely
because their source rows parse correctly. No dashboard/result was added.

## What you should test

Open http://127.0.0.1:3037/finance/imports using the same isolated reviewer.
The QA reviewer has import capability for this test; no real user grant changed.

1. Choose QA financial company / Banco Popular - Cuenta operativa (DOP), then
   your original Popular CSV. Save bank preview. Check both sections and compare
   credits/debits with the source. No financial records should be created.
2. Save the same file again. Both history entries remain; the newer one points
   to the earlier identical preview. Counts within either preview stay unchanged.
   Different overlapping files may also be previewed, but transaction overlap
   resolution is not implemented yet.
3. Choose QA spain company / Caixa - Cuenta operativa (EUR), then the original
   Caixa CSV. Confirm positive/negative signs, dates, balances and source cells.
   Change accounts and verify the history and selected preview change together.
4. Inspect Invalid transaction rows and All source rows. Source cells preserve
   the original values. A malformed row should not remove other valid rows.
   Download original CSV if desired; it should match the uploaded bytes.

Existing synthetic previews: DO #1/#2 identical valid Popular; #3 includes one
invalid row; #4 deliberately demonstrates a Caixa file under Popular format
(failed header check); ES #5 valid Caixa. These are disposable QA examples, not
real financial data. Its EUR 36 fee is a synthetic fixture, not confirmation of
the approximate Caixa commercial fee or its frequency. The exact pilot month
will be selected when enriched migration is prepared.

## Validation

- 198 PostgreSQL 16 tests passed: 117 finance/access/config/import and 81 existing
  analytics/purchase/import regressions. New reader/API coverage: 14 tests.
- The same 14 focused reader/API tests passed on isolated SQLite.
- Django check and makemigrations --check --dry-run clean. Frontend lint and
  production build passed, with existing unrelated lint warnings only.
- Read-only adapter validation against original external files: Popular 175 valid,
  0 invalid, 100 credits/75 debits; totals DOP 2,637,891.36 / 2,491,914.56.
  Caixa 154 valid, 0 invalid, 86 credits/68 debits; EUR 45,351.16 / 41,260.92.
  Observed ranges September 1–15 and July 1–October 7, 2026, respectively.
  No originals were edited, committed or saved into QA upload history.
- Browser: synthetic uploads, repeated occurrences, identical reupload, malformed
  row/filter, wrong-format file error, raw cells and account isolation verified.
  Screenshot /private/tmp/finance-phase3-1-bank-preview.png inspected.
- Logs: /private/tmp/finance-phase3-1-{focused,pg-tests,lint,build}.log.
- Existing legacy core_data.tests imports removed Center (documented in 2.4).
  Supported regression modules above passed; no claim all legacy discovery works.

Only temporary QA/test databases migrated. QA setup added a synthetic EUR account
and import grant for finance-review@example.test; normal/production data and
permissions untouched. QA frontend 3037/backend 8027 remain available. Original
private files remain outside Git, no credentials committed, unrelated exports/
untouched. No external review agent used. No push, merge or production deployment.

Apply migration 0006 before updated backend traffic, even when finance is hidden.
Back up the database for future production rollout; it now owns retained source
bytes as well as parsed preview history. This is not deployment authorization.
Next gate: client acceptance of this preview step, then bank movement commit and
overlap/undo delivery under the agreed workflow.

Phase 3.1 implementation checkpoints: backend `472d66c`, frontend `d0b3250`.
