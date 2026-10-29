# Manual payment identity review — no reimport for a missing number

D-094, delivered locally2026-10-28; client acceptance pending. Supersedes the D-093
requirement to obtain/reupload payment numbers for otherwise complete April23 rows.

## Business policy and workflow

The Alegra payment number is useful for automatic identity, but its absence must not
prevent deliberate recognition of an otherwise complete reported payment. Source
invoice/date/customer/amount/currency remain the evidence. No Excel edit, synthetic
Alegra number, deletion or repeated full import is required.

Existing uploaded/payment-posted report → Show payments needing identity review →
Review payment identity. View the source row, invoice reference, date, client, amount,
method and missing number. Choose Accept payment without number or Link existing
payment. A comment is optional; actor/time/decision/source evidence are always audited.

Candidates are scoped to company/provider. Linking requires agreement on invoice,
date, client, amount, currency and transaction kind, and no receipt reconciliation.
Existing studio/method assignments and source facts are preserved. When candidate
payments exist, creating another requires explicit confirmation that it is a separate
additional payment. Equal-value split payments are not silently collapsed. Name/amount
invoice-link review, cancellation, assignments and reconciliation rules still apply.
Accepting identity does not clear those independent warnings or check a daily closure.

Malformed dates/amounts, duplicate or invalid reported numbers, unsupported transaction
kinds/status/currency, bad invoice references and formula/cell errors cannot be waived by
this action. Valid records import normally; missing-number rows remain reviewable even
after the original report has been posted. Missing client identity still needs source
review. No new privileges: require full source visibility and import+edit capabilities.

## Overlap and internal identity

Use a reserved manual-UUID internal receipt key only; original source.number remains
blank and raw row/file remains unchanged. Screens show Manual #record-id to distinguish
an app reference from an Alegra number. No schema migration or source-column changes.

Anonymous overlapping rows require explicit linking/separate-occurrence confirmation.
Later numbered exports referencing a manually accepted invoice do not automatically
create another payment, even when dates/amounts differ. They stay in identity review.
An exact explicit link records a PaymentDecision alias for the newly reported number,
so later unchanged overlaps reuse that receipt. Other changed source facts remain under
normal source-change review; aliases never rewrite the first source or classifications.
Alias collisions fail closed under the shared company lock. Undone alias support can
require a fresh review; it must never create an automatic duplicate.

Review action uses a current company plan token, checks row membership/posting state,
validates again on save and records before/source/after, user, time and optional comment.
Retries of the same completed decision do not create receipts/events again. Source
fields cannot be submitted through the identity endpoint. Undo recognizes manually
created receipts, preserving existing reconciliation/edit/other-import protections.

Implementation: payment_identity.py, shared payment_posting plan/commit/undo,
payment-imports/{id}/resolve-identity/. Manual buttons/filter are available in both
Upload reports and historical/advanced payment import views. Accepted missing-number
warnings are no longer shown as unresolved; the original issue remains in source data.
Accepted receipts contribute to expected collections once using the normal method/fee
logic. They do not create invoices, bank/cash actual receipts or extra revenue.

## Validation / current client example

365 PostgreSQL finance regression tests passed; final identity/closure tests17 passed.
Tests cover immutable source, manual acceptance/audit/retry, same-fact overlaps,
numbered-report alias reuse, changed amount overlaps, explicit separate occurrences,
invalid data/access/stale/source-write rejection, filtering/undo and closure inclusion.
Frontend lint/build passed. Browser verified row2268 / B0200002153,1,564.00 / April23,
with no number entry required and optional comment. No working review was confirmed.

Private snapshot/rehearsal evidence:
.local-backups/payment-identity-review-20261028/{backup,rehearsal}.sqlite3 and result.json.
All14 April23 rows2268–2281 accepted and linked on the disposable copy. Payments4,984
→4,998; all original blank numbers and source rows retained. Every existing invoice,
payment source/assignment/link and bank movement source unchanged. Working dataset
left at4,995 active invoices/4,984 payments; owner restored the invoices before this
rehearsal. Acceptance decisions are left for the owner in the running local app.

No reset, new report upload, real financial transaction, source workbook alteration,
production change, merge, push, deployment or permissions change.
