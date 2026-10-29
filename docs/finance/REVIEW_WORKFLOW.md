# Operational review and access workflow

D-095 · 2026-10-29 · DR operational V1, before release. Supersedes earlier behavior
that allowed editors to change already reviewed classifications or recheck a closed day.

## Business rules

A supervised migration is already reviewed business information. Complete historical
entries start reviewed. Missing invoice-level payment-method mapping is not a reason
to review an invoice when its payment records supply the actual methods. Historical
studio can come from the mapped invoice fields or an unambiguous studio in its
supervised payments. Original report facts and mapping warnings remain available.
Supervision accepts historical customer aliases only when scoped invoice number,
currency and aggregate payments agree; financial differences remain pending.

Important missing information keeps an entry pending:

- Expense: movement type, expense month, category/subcategory when applicable, and
  studio or administration. Internal movements/refunds use their existing requirements.
- Income: movement type, studio/administration where applicable, and payment method
  plus operation date for ordinary customer income. Debit payment method/terminal
  are optional; credits do not require expense categories.
- Invoice: invoice date, studio, payment records with method/effective studio and
  resolved invoice links. Actual cost-center/price-list conflict and unresolved
  cancellation treatment remain pending. Amount/status/currency issues retain their
  existing resolution process.

Routine imports start pending even if their automatic assignments are complete.
An editor finishes the assignments and explicitly marks the entry reviewed. Reviewing
an invoice reviews and locks its active associated payments as one unit. Bank/cash
income and expense review uses the existing recognized/reviewed checkbox and Save.
Review does not set financial reconciliation flags.

Reviewed records are read-only. Editors cannot uncheck review or change assignments,
manual facts, source corrections, cancellation treatment or matching approval until
an authorized person explicitly reopens the entry. Reopening is audited with actor,
time and before/after status. An invoice reopen unlocks its payments. It does not erase
source evidence or previous review history. Historical refresh never automatically
relocks explicitly reopened work. Changed source facts still use source-change review;
unchanged overlapping reports preserve existing assignments and review status.
A new payment against a reviewed invoice waits for that invoice to be reopened.
Import undo also protects reviewed records; other existing audit/reconciliation/linked
source protections can still prevent undo after reopening.

A day can be checked/closed by an editor. Only a reopener can reopen a checked day,
including a day marked as needing recheck after its supporting data changes.
An identical retry of the existing check is idempotent; it does not replace the check.

## Permission mapping

| Capability | Authorizes |
| --- | --- |
| `can_import_finance` | Upload and commit routine bank/Alegra reports |
| `can_import_finance_migration` | Upload/prepare/commit supervised historical migrations, including their derived bank/sales/payment batches |
| `can_edit_finance` | Create/edit operational entries, classify/review invoices and payments, resolve source/matching issues, check/close days |
| `can_reopen_finance` | Explicitly reopen reviewed entries and checked days |
| `can_manage_finance_settings` | Existing company/account/terminal/category/mapping/fee configuration management |

Existing finance entry, monetary visibility, sensitive-detail and company/site/account
scope gates still apply. User and group grants combine using existing access rules.
The two new capabilities default to false; no existing partner grants are expanded.
The legacy `can_reconcile_finance` field is retained in storage/API for compatibility,
removed from permission controls, and is no longer
needed for the operational review and day-check workflow. Period closing remains a
separate deferred feature.

## Upgrade and handover

Apply core_data/finance migrations `0021_finance_review_workflow`. Back up the database.
For already-posted supervised workbooks, preview the audited upgrade explicitly:

```sh
python manage.py complete_supervised_reviews --company COMPANY_ID --actor USER_ID
python manage.py complete_supervised_reviews --company COMPANY_ID --actor USER_ID --apply
```

The default command rolls its preview back. It preserves raw sources and existing
manual assignments, fills only unambiguous missing historical studios, records audit
events, completes eligible historical invoice/payment groups, and leaves important gaps
pending. Future supervised imports run the same business rules automatically after
invoice/payment linking. Assign the new capabilities deliberately in user/group settings.

Local acceptance uses the separate QA SQLite database, never the normal production
connection. Private backup/rehearsal files belong outside Git. Release still requires
September overlap/comparison acceptance and the existing DR cutover checklist.
