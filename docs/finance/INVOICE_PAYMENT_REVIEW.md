# Permanent invoice/payment matching and review

Delivered locally 2026-10-28; D-091. Client acceptance pending.

## Business rule

Invoice references match exactly within the same company and source provider. Compare
an invoice total with the sum of all active payments referencing it, including split
payments. This is an invoice/payment comparison, not the net bank settlement after fees.

- Matching number, aggregate total and customer name: link automatically.
- Matching number and aggregate total, different customer/contact names: require an
  explicit name confirmation. Alegra can report a contact name in one report and a
  company name in another. Neither source value is replaced. The rule is independent
  of invoice prefix; do not infer fiscal invoice type from this matching policy.
- Same number, different aggregate amount: keep an amount warning and require a manual
  decision. Users can correct the source through the existing import/source-review
  workflow or explicitly accept the reported difference with a reason. Acceptance
  links the reported payments; it does not change the invoice, payment amounts,
  create a balancing transaction, write off a remainder or mark a daily closure Checked.
- Missing/invalid invoice, unpaid/cancelled invoice, currency conflict and reconciled
  evidence retain their protections. A customer-name confirmation cannot override them.

An excess is evaluated across the complete group; do not automatically link a convenient
subset that happens to equal the invoice total. Existing links remain traceable if new
source evidence creates a warning. Amount/name exceptions need a current explicit review.

## Operator workflow

Records → Invoices or Payment matching review → open an invoice/payment. The dialog
shows both original names, invoice amount, every candidate payment, combined amount
and difference. Choose Confirm name difference or Accept reported total difference.
The second action requires a reason. A confirmed decision can be reopened. Names-only
confirmation has an optional comment, avoiding redundant typing for supervised history.
The table payment count represents approved links; the dialog also includes unlinked
candidates sharing the invoice reference.

Existing records can be reevaluated with Refresh invoice/payment matches. Routine invoice
and payment posting/undo already invoke the same standing rules automatically, regardless
of upload order. Refresh does not approve exceptions on behalf of the operator.

## Integrity and access

New FinancialSale.payment_link_review JSON field, migration0020. Decisions bind a digest
to the exact invoice source/items and full active payment set. Changes to these facts
invalidate the approval; studio/channel assignment alone does not. Company locks and
expected digest prevent stale confirmation. Audit records retain user, time, decision,
reason and before/after evidence for the invoice and all affected payments. Retrying a
current acceptance does not duplicate review events. Source facts remain read-only.

Review and refresh require can_reconcile_finance and existing finance/money/bank/sensitive
visibility and full-company scope. No role/grant expansion. Paid/status/currency and
reconciliation gates are rechecked when saving. Original imports remain available.

## Validation and current local state

350 PostgreSQL finance tests passed; final workspace/matching tests16 passed after query
adjustments. Changed frontend lint and production build passed. Tests cover split totals,
name/amount confirmation, mandatory difference reason, stale approval/payment additions,
reopen/retry/audit, permissions and scope, cancellation/currency/reconciliation gates,
source preservation and candidate visibility. Browser checked name and amount dialogs
without approving real customer cases.

Consistent private backup and rehearsal:
.local-backups/invoice-payment-rule-20261028/{before,rehearsal}.sqlite3.
Migration0020 and refresh rehearsed on copy, then applied to local QA only. All4,881
invoices,4,984 receipts and2,351 movements and their original facts/assignments preserved.
Refresh changed3 receipt warnings; repeat changed0. Current receipt warnings:17 name,
2 underpaid,1 overpaid,116 missing/invalid invoice,1 cancelled. No exceptions accepted.
Examples: B0200000110 names differ but6,800.00 agrees; B0200002104 invoice3,060.00 versus
3,600.00 paid. Missing-total source rows remain unresolved; this feature does not invent
the114 missing invoice totals identified in SUPERVISED_BASELINE_LINK_AUDIT.md.

No source workbook, production database, reset, permissions, merge, push or deployment.
