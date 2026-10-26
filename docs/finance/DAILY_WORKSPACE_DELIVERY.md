# Daily finance workspace: first operational UI delivery

Date: 2026-10-25 (client timezone). Implements the navigation/browsing part of
D-071/D-072 and the invoice/payment edit dialog. Client acceptance pending.
Both repositories remain on feature/finance-phase-2. No push, merge or deployment.

## What changed

Finance landing now opens Records rather than separate import buttons and company
cards. Shared navigation provides Records, Upload reports, Settings (when allowed)
and Initial setup. Company selection carries between Records and Upload using the
URL; no test-company default is silently selected. Existing company/report IDs,
history, originals and previous import URLs remain intact. Company cards removed;
QA entities themselves were not deleted or hidden by name. Real uploads currently
stored under a QA-labelled company were not moved or renamed during UI work.

Records has three primary tabs: bank debits, bank credits and invoices. These are
current active ledger records across all imports, not saved preview rows. Query
filters apply before pagination, sorting and totals: company, actual source date
range, search, account (bank), invoice studio, payment method and supported review/
reconciliation state. Header controls sort date, amount and number. Source amounts
are labelled as amounts rather than profit or verified bank balances. EUR/DOP are
not combined. Original source information is readable in dialogs, with links to
existing import decisions/undo/full history. Existing report downloads remain
behind their import capability.

The invoice table shows one invoice total, studio, linked payment count, payment
method summary and review state. Opening a row shows protected invoice facts,
original item occurrences, editable invoice studio, and zero/one/many payments.
Each payment exposes current method/studio and a correction reason/save action in
that dialog, plus original evidence and audit history. Payment facts remain locked.
A payment studio can be manually overridden or set to inherit the invoice studio.
Dynamic inherited studio follows later invoice assignments; manual overrides do
not change siblings/invoice facts and survive reimports. Studio-only edits preserve
the current method, including a previously corrected Recurring method. Saves show
feedback without closing the dialog. Existing revision, reconciliation, company
scope, edit permission, source identity and protected undo behavior still apply.

Payments without invoices remain reachable using Payments awaiting invoice inside
the Invoices workspace. They can be inspected/edited without placeholder invoices.
Invoice/payment receipt counts and amounts do not imply actual bank reconciliation.
Ordinary assignment endpoints explicitly reject submitted source-fact fields rather
than silently accepting a UI attempt to alter amount/client/code.

Upload reports is one page using the existing upload, processing-plan and commit
endpoints. Dominican types are exactly combined bank report, Alegra invoices/items,
and Alegra transactions/payments. Bank account appears only for bank uploads; the
verified provider follows company country. Original CSV bank/invoice and XLSX/CSV
payment readers remain unchanged. Show file name, actual observed range, source
rows/totals, readable preview, original evidence/issues, one confirm step and a View
all records link. Missing classifications do not become an extra upload prerequisite.
History is collapsed/secondary. Failed payment previews can re-read saved originals;
valid and pending source rows continue to use the existing guarded posting service.
Egreso rows are labelled Purchase / outside payment import, separately from source
correction counts; they remain unposted as before. No purchase matching added.

Old screens remain reachable for full conflict resolution and protected undo. Bank
and sales legacy screens now accept exact batch deep links, matching payments.
Review decisions have not been rewritten behind a new UI. All new copy has EN/ES
translations. Spain retains Caixa bank import and the existing Mindbody sales policy;
this delivery does not invent a Spanish Alegra adapter or duplicate Mindbody upload.

## Backend additions and boundaries

- GET /api/finance/workspace/options/ and workspace/ provide company-scoped,
  sensitive-detail-protected read-only presentation queries. Bank/account privacy
  uses existing visible_accounts; invoice/payment scope reuses existing contracts.
  Partial-studio access cannot retrieve full company rows, raw sources or totals.
  Payment details/method filters additionally require the existing bank-detail gate.
  Filters and aggregate amounts apply to the full query before pagination. Receipt
  counts use correlated queries, so filtering by method does not multiply invoices.
- Existing receipts list accepts an invoice filter; serializers include their real
  source filename/batch. Payment previews expose computed date coverage and separate
  excluded-purchase counts. These are read-only presentation additions, not source
  snapshot rewrites. Payment plan rows expose original customer/kind for clear UI.
- Existing audited receipt assignment action now allows an optional studio override
  or clearing it to invoice inheritance, preserving unrelated assignments. Uses the
  existing company lock, revision checks, edit capability, audited event and undo
  protection. This is the small missing capability needed by the requested dialog.
- No schema/data migration, permission grant, new dependency or import interpretation
  change. Deduplication, posting, links, source corrections and calculations reused.

## Validation

Full supported PostgreSQL regression: 313 tests passed. SQLite: 313 found, 307
passed and six existing PostgreSQL-only race tests skipped. Final PostgreSQL focused
run: 50 tests passed after presentation/query refinements. Six new workspace tests
cover invoice totals once with multiple payments, full-query date/search/method/
review filters, bank direction/account isolation, sensitive/company/studio privacy,
unlinked → linked queries, payment studio inheritance/override, wrong-site/stale/
reconciled edits, explicit read-only facts, reimport preservation and edit grants.
Existing native-XLSX test also checks excluded count and observed date coverage.

Frontend lint/build passed with existing unrelated warnings. Django system and
migration checks passed; no migration changes. Logs:
/private/tmp/finance-workspace-{regression,pg,pg-focused,lint,build}.log.

Browser used synthetic company #6 only: invoice B0200009001 total300 retains two
payments, 100 Recurring + 200 Cash; changed receipt990001 studio from historical
manual assignment to invoice inheritance with a reason, preserving Recurring and
original source facts. Source evidence shows the real report filename. Unified
Upload selected all three available Dominican report types and reopened synthetic
native preview #6. Confirm imported receipts101/102, total3600, leaving one expense
outside payment posting. They have no matching invoice, and appear in Records /
Payments awaiting invoice. Synthetic company now has four active receipts; its
invoice still totals300 once. No real report was posted or edited.
Real failed report #4 remains unchanged, zero parsed rows, missing_payment_header,
no PaymentPosting; client can re-read it with the corrected reader when ready.

Screenshots (synthetic data only): /private/tmp/finance-workspace-invoice.png and
/private/tmp/finance-workspace-upload.png. Browser upload chooser was not used to
upload real files. Existing multipart API tests cover file submission/overlap;
browser exercises saved-source preview, real confirmation path and record editing.

## What remains / not delivered

This is the first daily-workspace delivery, not completion of all UX-1–4/Phase4.
Bank expense classifications, manual descriptions/periods/operation dates, terminal
corrections, manual cash entry, create/void permissions and bank edit dialogs still
need their planned underlying assignment services. The bank screen explicitly
states this; no nonfunctional Create/Delete buttons or fake classification filter.
The dedicated pending source conflict/correction actions and Undo remain on the
preserved detailed import screens behind a contextual secondary link. Cross-import
records browsing is delivered; a unified pending queue/upload-membership filter,
fixture isolation and later fully embedded conflict/undo controls remain follow-ups.

Historical financial migration, September certification, allocation, actual bank
reconciliation, Spain sales adapter, results/charts and production release are
still their separate remaining phases. Reconciled filters read stored state only;
no reconciliation can be fabricated from import recognition or equal totals.

## Client test

Open http://127.0.0.1:3037/finance (same QA credentials). For a safe synthetic test,
select Receipt posting synthetic QA; it is a test company, not a production entity.

1. Invoices shows one row B0200009001 /300DOP /two payments /Cash + Recurring.
   Filter/search/sort, then clear the search. Amount remains300 once.
2. Open it; inspect items and the two payments. Change a permitted payment method
   or studio with a reason. Save; dialog stays open and facts remain locked. Inspect
   original information and correction history, then close/reopen to verify.
3. Payments awaiting invoice shows the two synthetic receipts101/102 /3600DOP.
   They remain separate from the 300 invoice and are not fabricated sales.
4. Upload reports retains company; choose Alegra transactions and expand history.
   Open native-header-synthetic-qa.xlsx #6: two Imported rows and one Purchase /
   outside payment import. Source information is readable; original downloads and
   full import decisions/undo remain available with the relevant permission.
5. Bank debit/credit tabs query current ledger records rather than previews. Use
   the appropriate existing company/account to inspect authorized data; empty
   tables are valid when reports are saved as previews but not yet posted.
6. For real report #4, select its existing company and Alegra transactions, open
   failed source history and Read saved report again. Review the new preview before
   confirming. No file reupload is required; this creates only a fresh preview.
