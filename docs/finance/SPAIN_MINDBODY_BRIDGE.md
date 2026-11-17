# Spain V2 Step 2 — source-linked Mindbody sales

Delivered locally 2026-11-15. Owner acceptance pending. Both repositories remain on
feature/finance-spain-v2, with no commits/pushes authorized or performed.

## Ownership and source selection

Spain/EUR Finance reads completed Mindbody `sales` imports for the company's
existing Analytics site. It does not create Alegra preview batches, copied sales,
or duplicate FinancialReceipt rows. Production sales become available from those
existing imports when the code/schema/configuration is deployed; no extra routine
upload is needed. This local delivery did not access or change production.

Use the most recently completed report containing each sale number, preserving its
whole item/payment group. Order by processed time then report ID. Do not sum all
SaleLine rows: the existing Analytics natural key includes amounts, method and date,
so corrected rows may coexist with older identities. Read preserved SaleRawRow
snapshots instead. This is isolated in finance/mindbody.py; Analytics import behavior
and analytics calculations are not changed by this delivery.

This relies on the agreed full date-range export: an included sale contains its full
item/payment group. Omission of an entire sale from a later weekly/partial-period
report is not a cancellation. Failed/processing imports cannot replace completed
source snapshots. Invalid rows with an identifiable sale number block review; rows
without a number remain Analytics import issues. Observed dates do not certify full
source or settlement coverage.

Company and site identity scope source numbers. Reject ambiguous active finance
companies on the same site, rather than silently count the same sales in two legal
entities. Initial authority is Mindbody only; Spain Alegra cutover remains deferred.
Do not apply Dominican fiscal-number rules to Mindbody sale numbers.

## Amounts, grouping and assignments

Retain sale/customer/date/source studio, each item and method-paid amounts. Group
payments by exact normalized source method; one sale can have several methods.
Recognize a repeated item on distinct method rows as one split-paid item only when
those slices sum exactly to that item's reported total. Other layouts retain their
rows and mismatches stay pending. October's real file validates same-method multi-
item sales, not a real split/refund layout; those still need Step 4 acceptance.

Source amounts/number/customer/date/items are read-only. Finance owns sale studio,
payment channel and optional per-payment studio override, with sale-studio inheritance.
Overrides are separate from Analytics and never written back there. A changed method
label does not silently reuse the correction for a different label. Existing alias
rules, manual corrections and source fields are distinct.

New complete consistent sales are implicitly reviewed/read-only. Missing studio or
method, configured review requirements, invalid source rows, conflicting dates/
customer IDs/studios, total mismatches and negative/refund amounts stay pending.
Refund interpretation remains Step 4; no cancellation is inferred from disappearance.

Reopening requires can_reopen_finance. Saving/completing review requires
can_edit_finance and payment access, with company activity, scope and sensitivity
checks. An explicit reopening stays pending across identical uploads. A later changed
source group makes a previously reviewed sale pending but keeps its lock: a privileged
reopen is required before editing/review. Previous source values and report history
remain visible. Even an implicitly auto-reviewed sale with no Finance action detects
changes against its earlier report versions. Source errors cannot be approved away.

Writes use a company lock and token covering source facts, effective mappings,
manual assignments and revision. Stale tabs fail with409 and must reload. Reads never
create assignment/audit rows. Changes to Analytics facts are reflected on the next
read, so there is no asynchronous synchronization job to fail silently or break an
Analytics upload. A concurrent import after a Finance write is detected as a source
change on the following read. Step 3 will include these source hashes in closure
checks; this delivery does not enable Spain closures.

## API, history and access

- Existing workspace endpoint returns Spain invoices as provider=mindbody sales,
  with date/client/amount/studio/method/review filters, sorting, pagination and totals.
- /api/finance/mindbody-sales/detail/?company=ID&code=SALE
- /api/finance/mindbody-sales/history/?company=ID&code=SALE
- POST assign/, reopen/, review/ using the same selection and expected_token.
- New finance migration0022 creates MindbodySaleAssignment and MindbodySaleEvent.

Source history is derived from existing completed Analytics reports and collapses
unchanged repeats. Finance edits/review/reopen are separate persisted events with
actor/time and before/after state. Payment history/method detail is hidden without
the existing bank/payment-view capability. Sensitive access and company-wide site
scope are required, matching the existing invoice workspace; partial studio grants
cannot access the whole company source. Generic Alegra upload/edit endpoints remain
DR-only, preserving their existing validation.

## Validation and local data

- Full finance suite:439 PostgreSQL tests passed before final history/redaction
  refinements; final12 Mindbody PostgreSQL cases passed after those refinements.
- Frontend changed files pass ESLint and the isolated production build passed.
- No migration drift; migration0022 applied to a backed-up local QA database.
- Existing Analytics importer loaded the supplied October sample into Finance QA ES
  (company QA spain company, site Finance QA ES). Original reports remain outside Git.
- Result:107 sales,116 items, EUR8,534.25; all107 reviewed. Card EUR6,692.60;
  Cash EUR1,841.65. Existing local bank records/configuration/permissions preserved.
- Disposable-copy rehearsal imported the real report twice more: unchanged token,
 107 sales, same total, preserved manual method override and reviewed status.
  Filtered107-sale workspace measured0.015s/41 SQL statements on the local SQLite
  copy; this is local evidence, not a production performance guarantee.
- Browser verified sales tab/count/total, multi-item sale1146 with one Cash payment,
  reviewed read-only state, source history and closing both dialogs without a crash.
  Browser checks did not edit the working Finance assignments.

Owner tests at http://127.0.0.1:3037/finance/records?company=3:

1. Select QA spain company -> Mindbody sales. October1–31 gives107 sales and8,534.25.
2. Filter Card:6,692.60; Cash:1,841.65 (the sample has one method per sale).
3. Open1146:129.00, two items, one Cash payment, read-only. Inspect original source
   and report history; close safely. Other multi-item examples include1067/1065.
4. Reopen a sale, change method or studio, save, close/reopen and confirm persistence.
   Restore the correct assignment and complete review; expect a read-only dialog.
5. Test review/status, date, studio, number/client filters and pagination.
6. Optional: reimport the same October Sales file through existing Analytics uploads
   into Finance QA ES, not the unrelated Spain site. Counts/totals and manual Finance
   corrections must stay stable. This is already rehearsed on a disposable copy.

Wait for owner feedback and explicit commit/progression before Step 3. No production
release, data reset, new permission grants or raw-file publication is part of Step 2.
