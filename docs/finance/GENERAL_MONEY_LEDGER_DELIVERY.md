# General money ledger and cash foundation

Follow-up: historical cash undo/restore and operational closure checks are now
implemented in [DR Operational Finance V1](DR_OPERATIONAL_RELEASE.md). The deferred
recovery statements below describe the original foundation checkpoint.

Delivery date: 2026-10-27. Implemented locally on `feature/finance-phase-2` in both
repositories. Client accepted the workflow on2026-10-27 after document comparison and successful
manual entry testing (D-084); no production deployment.

## Accepted business definition (D-083)

Finance tracks general actual income and expenses, including bank and cash. Bank
statements are one source of actual movements; invoices and their payments are
separate sales evidence. Recording an invoice must not automatically create a cash
receipt or count revenue twice.

1. Start with one general cash account per company; studio cash accounts can be
   configured later using existing participating-studio restrictions.
2. Record actual cash received manually, one entry at a time.
3. Historical expenses default to the selected bank account because the workbook
   cannot identify their cash origin reliably. New expenses select **Account from**;
   incoming entries select **Account received into**. The workbook's explicit
   Efectivo income rows can be migrated into a cash account separately.
4. Manual cash receipts represent money actually received, not a promise to pay or
   an automatically generated copy of an Alegra payment.
5. Cash opening balances remain unknown/unverified until separately established.
   Unknown must not be treated as zero.

Cash deposits and transfers between own accounts retain the previously agreed
internal-movement treatment: principal is excluded from income/expense/profit;
associated fees are expenses. A paired transfer workflow is not delivered here.

## What changed

Records now presents **Expenses · Income · Invoices**. Expense and income tabs
include all visible financial accounts, account and origin filters, and manual
creation. Source labels distinguish a manual entry, a routine report and a
historical migration, retaining report name/source row where available.

Manual forms allow bank or cash accounts, date, positive amount and concept, plus
business classifications. Expenses include studio/administration, category,
subcategory and expense month. Income includes studio, payment method and operation
date. Cash accounts force the cash payment method and cannot use a terminal.
Incomplete assignments can be saved without a mandatory comment; Reviewed stays
unavailable until required classifications are complete.

Unlinked, unreconciled manual entries can be edited, including account, date and
amount, with an audit trail and stale-edit protection. They can be voided with a
reason; this is logical deactivation, not physical deletion. Imported amounts,
dates and descriptions remain read-only while business assignments stay editable.
An explicit bank-report link protects the linked manual entry's financial facts.

Creating a general cash account is explicit and idempotent. It creates a software
ledger account only, without establishing a verified balance or opening a financial
institution account. Account kind cannot change after movements exist.

The historical preview has a **Cash income migration** section. It imports only
explicit Efectivo/Cash credits, discards workbook bank balances for those entries,
preserves available source assignments and retains lineage. It does not infer a
studio from free text when no mapped location exists; complete missing assignments
in Records after import. Repeat submissions and copied previews of the same source
cannot duplicate cash rows. Possible overlaps against another workbook/manual cash
entry remain pending. Equal genuine occurrences within one workbook stay distinct.
A studio-specific cash account cannot absorb another studio's historical rows.

Manual bank entries are included in statement overlap review. Possible matches
require a decision instead of silently duplicating or overwriting the manual entry.
A subsequent exact repeat of an explicitly linked report row retains that link.

## Implementation and permissions

The existing `BankMovement` physical model/table is retained as the shared actual
money ledger to preserve existing posting, classifications, source protection and
history. Migration0017 adds nullable source lineage and unique manual/migration keys;
existing bank rows keep their values. `BankEvent.posting` can be null for entries
that are not created through bank report posting.

Public routes added:

- `/api/finance/movements/`: existing reads/assignments plus manual create.
- `/api/finance/movements/{id}/edit-entry/` and `/void/`: manual entry operations.
- `/api/finance/companies/{id}/general-cash/`: explicit general account setup.
- `/api/finance/migration-imports/{id}/cash-preview/` and `/import-cash/`.

The old bank movement route remains compatible. Existing company, allowed-site,
studio, money-visibility and sensitive-category controls remain in force. The legacy
capability name `can_view_finance_bank_accounts` still gates financial-account access;
`can_edit_finance` permits manual creation/edit/void, `can_import_finance` cash
migration and `can_manage_finance_settings` general cash account creation.

## Validation and local data preservation

- Fresh PostgreSQL suite: **285 finance tests passed**, including manual idempotency,
  equal receipts, source protection, permissions, studio/account boundaries,
  migration retries/overlaps, audit/void and manual-bank linkage.
- Changed frontend files lint and production build passed. Migration drift and
  whitespace checks passed.
- Applied0017 only to persistent local QA after an integrity-checked private backup:
  `.local-backups/before-cash-ledger-20261027T162133Z` under the project root.
  Canonical comparisons by column name proved existing movements, classifications,
  invoices, payments, bank decisions and events unchanged. SQLite reordered event
  columns during schema alteration; values remained identical.
- Browser verified the three Records tabs, explicit general cash setup, expense
  Account from form/unverified-balance message and actual workbook cash preview.
- Local company1 now has account6, **General cash (DOP)**, with unknown opening
  balance/date. No actual cash entries were posted and no synthetic money records
  were inserted into the working client dataset.
- Workbook8 cash preview: **4 new receipts, 26,860.00 DOP**, dates August4, August6,
  August13 and September1. All remain unposted for client review.
- Existing counts remain **483 actual movements, 744 invoices, 745 payments**.
  The previously audited10 pending bank overlaps were not resolved by this delivery.

## What the client should test

1. Open Records for the working company. Check Expenses, Income and Invoices,
   account filters and Origin filters.
2. Create one actual cash receipt under Income using General cash (DOP); select
   studio and operation date. Check that this does not create another invoice.
3. Create one cash expense, choosing Account from, category/subcategory, studio or
   administration and the correct expense month. Verify partial save versus Reviewed.
4. Reopen a manual entry and check its editable facts and audit history. Void only
   a disposable test entry with a reason. Imported financial facts stay read-only.
5. In Initial setup, open workbook8 and Cash income migration. Review the four
   receipts and total above before confirming import. Then complete missing studio
   assignments in Records; repeating the preview must show Already imported.
6. Verify existing bank classifications and invoice/payment records remain present.

## Limits and next phase

This delivers actual cash/bank records needed for future closures. It does **not**
yet deliver cash-to-Alegra matching/closure comparisons, certified running cash
balances, paired account transfers, monthly results or full historical certification.
Cash migration has no dedicated undo/source-correction screen yet; do not assume the
bank import undo action covers this new path. Imported cash financial facts remain
protected. Existing bank overlap ranking/whitespace issues remain separate follow-up
work. Do not reset, re-post the bank workbook, deploy or merge solely because these
checks passed.
