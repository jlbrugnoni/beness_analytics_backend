# DR operational MVP — current release recommendation

2026-10-29. Owner has uploaded the current September bank and Alegra reports and
asks whether to release. Recommendation: proceed to a controlled DR operational MVP
cutover after the final operational acceptance sample and production deployment
checks. No further large operational feature is proposed. This is a readiness
assessment, not authorization to merge, push or deploy, nor a reconciled-month claim.

## Current source/import evidence

Audited a consistent private snapshot with SQLite query_only enabled. No working
financial record, classification, import decision, permission or day check changed.
Private evidence: workspace `.local-backups/release-readiness-20261029/`; do not commit.
Company1 remains QA financial company and must not be copied wholesale to production.

- Bank25: September1–15,175created entries; active, no parser errors/pending decisions.
- Bank26: September14–30,117created entries and53linked overlaps; active, no parser
  errors/pending decisions. Combined292September bank entries:129debits/163credits.
- No identical active September movement groups for account/date/amount/description/
  balance. This is the explicit comparison check, not a guarantee against every
  possible semantically duplicated transaction.
- Sales15:611September invoices, September1–30; all created without pending decisions.
- Payments14:615September customer payments; all linked to invoices. The67excluded
  source rows are all Egreso, correctly omitted from customer income.
- Invoice total and payment total both3,555,130.80DOP.607invoices have one payment,
  four have two payments. Zero per-invoice aggregate differences or missing effective
  payment studios (payment studio inherits invoice studio where configured).

## Operational processing is still pending

Routine entries intentionally arrive unreviewed. CurrentSeptember has611unreviewed
invoices/615unreviewed payments.475card payments retain method-review ambiguity
(Cierre versus recurrent); those are business reviews, not import failures.

Only4of129expenses and1of163income movements are reviewed.125expenses lack studio,
category and expense period;162income movements lack operation date;51lack studio/
payment method. Consequently most received money is not yet assigned to September
closure days. Zero card actuals in the current closure view must not be interpreted
as evidence of missing money. September cash from Alegra is expected income and does
not itself create actual cash received.

There are no checkedSeptember days in the current comparison. Before launch acceptance,
complete one representative operating day end to end (payment review, bank dates/
methods/studios, actual cash as evidenced, expense classification and check/reopen).
Full September classification/reconciliation remains operational work; an entirely
empty review queue is not a requirement for releasing software intended to process it.
The client's older closure acceptance applies to earlier reset datasets.

## Technical and production gates

Latest full finance regression run:380PostgreSQL tests passed. Frontend production
build/lint passed for the description/UI changes; the later Import details runtime
fix was verified from both income/expense links and with explicit no-undef lint on
bank/sales/payment import pages. The pre-existing core_data/tests.py Center import
error remains documented separately; no whole-project green-suite claim is made.

Changes are still uncommitted on feature/finance-phase-2 in both repositories.
Final release work consists of reviewing/committing the intended files (exclude
private databases, original reports and user-owned exports/), rehearsing target
PostgreSQL backup/restore and migrations, configuring actual company/account/studio/
terminal/fee records and owner-selected partner grants, then authorized merge/deploy
of compatible backend/frontend. FINANCE_ENABLED and the frontend API build target
must be set for the actual environment. Do not ship the local test database or QA
credentials/configuration as production data.

Use REVIEW_WORKFLOW.md for the current permission policy: routine upload, migration
upload, edit/review/close-day, separate reopen-entry/day, and settings management.
This supersedes old references to can_reconcile_finance for operational checks.
Use DR_V1_CUTOVER_RUNBOOK.md for the detailed backup/deployment/recovery procedure.
If upgrading an environment with old finance data, review the explicit supervised
completion and expense-description repair commands before enabling users.

Scope: Dominican operational finance only. Spain remainsV2; analytics follows Spain.
