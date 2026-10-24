# Finance screen and workflow specification

Status: Phase 0 accepted, 2026-10-24. These describe the target screen flows.
Phase 1 implements finance landing, group capabilities and user grants/effective
access. Import, transaction, configuration and result flows remain future work.

## Entry and setup

Finance navigation requires financial view, money visibility, and appropriate
location scope. Expose only available actions. Add group capability editing and
effective/inherited permission display in existing user management.

Configuration flow: company -> account -> terminals/studio mappings -> editable
categories/subcategories -> source/payment/fee/tax rules. Start DR with the
recommended Banco Popular operating-account label; leave setup values editable.
Mark sensitive categories and define operating/extraordinary/shared treatment.
Use real source layouts without committing private financial files to Git.

## Imports

Choose routine source import or historical migration, then company/account/source.
For migration, map existing enriched columns and match existing studios; propose
missing configuration for confirmation. Show preview counts/totals and issues.
After commit, show imported/updated/unchanged/pending rows and links to their review
tasks. Preserve the original file name, batch, raw row, and history.

Popular reader handles two debit/credit sections. Caixa reader handles signed
EUR values. Alegra reader groups invoice items and counts invoice totals once.
Spain uses already imported Mindbody Sales through an adapter; finance does not
ask for a duplicate routine sales upload. Future Spain Alegra adoption requires
one authoritative source/cutover and validation of unnamed consumer invoices.

Reupload, reordered rows, partial periods, and manually entered bank records must
not duplicate genuine movements. Missing rows in a later partial file are not
deletions. Invalid/ambiguous records remain reviewable while independent valid
records import. Import commit rechecks stale preview/source versions.

## Manual entry and review

Income/Expenses provide Create manually and Import report actions. Manual entry
sets account/company, date, amount/currency, description, kind, and relevant
period/studio/channel/category. Show missing optional assignments as review work
rather than fabricate values. Keep Manual/Imported/Migrated labels visible.

Review table: bank date, operation date or expense period, amount, business
description, studio/channel/category, origin/report, and separate review/match
statuses. Open record to view original versus assigned fields and history.
Imported records edited manually retain original origin. Bulk editing checks all
affected rows' scopes and stale versions, not only the table filter.

Sensitive categories display authorized category totals but no individual payment
rows or identifying details without the extra capability. Protect searches,
history, match candidates, exports, and raw files as well as screen text.

## Internal movement and fee reimbursement

Own-company cash deposits and operating-to-savings transfers remain bank/cash
movements outside sales/profit. Assign source/destination and link counterpart
when available. Unimported savings counterpart stays pending; do not create a
verified destination balance. Charges associated with transfer remain expenses.

Caixa fee reimbursement is a different kind: keep the fee debit and reimbursement
credit, link the reviewed offset, and show both without treating reimbursement as
a sale. Unknown AZUL fees are review items; do not assume they are additional
withholding or ignore them to improve reconciliation.

## Reconciliation and refunds

Select company/studio/period/channel. Compare source sales with expected fees and
net receipts assigned by operation date. Drill into sales and bank movements;
suggest grouped/partial matches. Users confirm, split, or leave unresolved with
notes; every nonzero difference remains recorded, including rounding candidates.

Refund entry/source update links to the original sale and adjusts its result
month. Actual returned money stays on its bank date/channel. Missing original
sale stays for review. Avoid applying both source cancellation and refund as two
reductions. Show the affected original month and revised administration weights.

## Administration and monthly results

Company-wide administration costs retain original category and expense period.
Preview allocations from that month's company gross sales including IVA before
fees. Show studio income, weight, and allocated amount only where authorized.
Restricted studio filters do not alter company-wide denominator calculations.
No-income month stays pending with manual split available. Apply deterministic
rounding so allocated amounts sum to the original expense; store provenance.

Monthly results show gross sales, processing fees, direct operating costs,
administration, operating result, extraordinary inflows/outflows, and final
management result. Drill-down respects sensitive detail and location access.
Company total never adds shared parent expense and allocation children together.
Explain income/expense source coverage; Spain expense-only historical periods
are incomplete, not evidence of a completed loss.

Initial v1 allows audited corrections; no mandatory Close month gate. Later
closing and net-of-tax reporting are separate enhancements. Do not describe
the custom final management result as EBITDA.

## Export and configuration changes

Exports require their own action permission and the same location/detail rules
as API views. Exports and original source downloads are different permissions;
sensitive raw files cannot bypass category-detail restrictions.

Renaming categories keeps existing references. Changing rates/mappings/tax defaults
does not silently restate historical records. Show affected periods before an
explicit recalculation and retain earlier values. Used configuration is archived
rather than deleted. Action audit is required throughout.
