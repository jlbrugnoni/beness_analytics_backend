# Phase 3.3.2 sales posting and cancellation review delivery

Date: 2026-10-25. Implemented and validated; client acceptance pending.
Backend/frontend branch: feature/finance-phase-2. No push, merge or deployment.

## What I did

- Recorded D-057/058 and BR-062/063: Anulada confirmed; cancellation may retain a
  payment for a replacement instead of a refund. Refund settlement is separate.
- Updated source parser to alegra-items-v2. New previews count paid and cancelled
  invoices separately. Paid totals exclude cancelled invoices. Unknown statuses
  and incomplete/inconsistent invoices remain review-only.
- Added migration 0009: Company.sales_revision, FinancialSale, SalesPosting,
  SalesDecision, SalesEvent. A partial unique constraint protects active company/
  provider/full invoice code. Reversed history remains and a fresh source may
  create a new active occurrence after an eligible undo.
- Added versioned alegra-posting-v1 interpretation of stored previews. V1 Anulada
  rows can be recognized at posting without rewriting old raw rows or summaries.
  Preserve every item, repeated tax/discount column occurrence and multiplicity.
  Compare complete item sets independently of report order; never deduplicate
  identical items. Client names do not identify invoices.
- Commit independently complete new invoices and link unchanged existing ones.
  Later known cancellation creates a pending decision until explicitly approved.
  Changed date/amount/client/items/studio/payment-source facts remain anomalies;
  retain current facts with a reason while investigating rather than replacing
  them here. Unknown/invalid invoices remain unposted and need corrected source.
  Missing rows never cancel sales; old paid files cannot silently restore them.
- First-seen cancelled invoices retain evidence with zero contribution. Approved
  cancellation keeps original invoice facts/date/items, changes status and logs
  before/after. Its bank refund is not fabricated. Results will later use original
  invoice month; this delivery exposes ledger contributions, not monthly profit.
- Snapshot studio/channel mapping on creation. Cost center remains primary;
  conflicts/unknown aliases/recurring ambiguity remain visible. Manual invoice
  assignments take precedence and survive retries/default edits. Editing only
  one field preserves the other field's existing value/origin/evidence; no default
  refresh silently restates older decisions.
- Cancellation treatment supports pending, refund expected, no refund, replacement.
  Replacement is another active paid invoice in the same company. Notes required;
  source facts remain immutable. This link is operator evidence, not automatic
  proof of matched bank settlement. It does not move cash or adjust tax/fees.
- Added processing/, commit/, resolve/, undo-preview/, undo/ under sales-imports;
  read-only /api/finance/sales/ with active/all/reversed, exact code lookup,
  company assignment options, per-sale history/ and POST assign/. Assignment and
  cancellation edits require edit permission; cancellation review also requires
  import. Existing source privacy/site-wide company gates protect every path.
- Company locks, sales revisions, configuration/rule revisions and decision/sale
  revisions protect writes. Same-batch repeat commit is idempotent. Concurrent
  stale overlaps reject with 409; active invoice uniqueness is also DB-enforced.
  Inactive companies cannot change sales. All responses are private/no-store.
- Undo requires import/edit plus financial posting ownership, or settings authority.
  Only untouched unreconciled creations without other active source dependencies
  reverse. Approved cancellations, edits, replacement targets and linked existing
  invoices stay protected. Raw source/history survives; retrying undo is safe.
  Partial undo freezes pending decisions; fresh previews are required after undo.
- Added EN/ES plan counts, confirmations, source comparisons, manual assignments,
  cancellation/replacement lookup, protected undo preview, recorded sales and
  paginated before/after history. Source parse and posting statuses stay separate.

## Validation

- PostgreSQL 16: 253 tests passed (172 finance + 81 existing analytics/purchase/
  import regressions). Includes 18 sales-posting tests: 16 API/behavior tests plus
  2 concurrent commit tests. Existing 18 sales-preview tests updated for Anulada.
- SQLite regression run before the final assignment-preservation case: 252 tests,
  248 passed and 4 PostgreSQL concurrency tests skipped. Final focused SQLite
  sales run: 36 tests, 34 passed and 2 PostgreSQL race tests skipped.
- PostgreSQL found an optional-studio outer-join lock failure during assignment;
  fixed by locking only FinancialSale using FOR UPDATE OF self. Final suite passed.
- Frontend lint/production build, Django system and migration consistency checks
  passed. Existing unrelated frontend warnings remain. No external review agent.
- Browser verified synthetic company Sales posting QA: base import #4, overlap #5
  reused both invoices and retained recurring override, cancellation #6 explicitly
  approved and linked replacement, invoice/history detail, untouched import #7
  posted and undone. No real user file was posted or undone by the agent.
- QA active invoices: B0200000901 Anulada/200 original amount/zero contribution,
  manual Recurrentes, replacement sale B0200000903; B0200000902 paid/100;
  B0200000903 paid/200. B0200000904 reversed/50/zero contribution.
  Active paid contribution is 300 DOP; no bank refund created.
- Screenshots: /private/tmp/finance-phase3-3-2-sales-ledger.png and
  /private/tmp/finance-phase3-3-2-sales-history.png. Synthetic private QA data only.
- Only isolated QA/test databases migrated. Normal/production DB and grants are
  unchanged. Previously uploaded QA files/bank postings were retained. Legacy
  core_data.tests still references removed Center; targeted regressions above pass.

## What you should test

Open http://127.0.0.1:3037/finance/sales-imports using the same finance QA login.
Select Sales posting QA for the existing synthetic examples, or your Dominican
QA company for an original report. Saving a preview still does not post sales.

1. Open a preview and click Import sales. Review company/file and plan counts,
   then confirm. New complete invoices appear once in Recorded sales. Upload the
   same/overlapping report again: existing invoices link, without duplicate sales.
2. Edit an invoice's channel to Recurrentes or correct its studio, with a reason.
   Repeat the source upload: manual choices remain. Mapping review/conflict
   explanations and original labels remain visible in the assignment dialog.
3. A later Anulada report keeps a current paid invoice pending until Review change
   and Approve cancellation. Date, amount/client and items remain intact; its
   contribution becomes zero. An old paid file cannot reactivate it automatically.
4. For an Anulada invoice, choose Refund expected, No refund or Replacement invoice.
   Replacement lookup uses its full code within the same company. Add a reason.
   No bank debit is created. Revisit history for original/approved/manual evidence.
5. Try Undo sales import on an untouched synthetic new upload. Preview eligible,
   reused and protected counts first. Reversed invoices remain under All/Reversed;
   protected manual/cancellation/replacement/reconciliation history stays intact.

## Remaining scope

Bank refund matching, fee calculations, company/studio period results, source
coverage certification and historical enriched migration remain later work.
An anomaly cannot be resolved here by editing invoice date/amount/client/items;
retain facts with a reason and investigate/re-export. Monthly closing is deferred.
Future reconciliation writers must take the same company lock, advance sales
revision and record audit so stale/undo guards remain effective. No production
release or real historical migration has been performed.
