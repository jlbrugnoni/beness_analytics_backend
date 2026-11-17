# Spain Finance V2 operational release

2026-11-16. Owner authorized deployment after Steps 1–4 testing and historical
migration audit. This releases operational finance; financial analytics is later.

## Verified before publication

- 462 finance tests passed on disposable PostgreSQL; none skipped.
- SQLite finance regression: 456 passed, six PostgreSQL-only skips.
- 18 Analytics import guard tests passed.
- Changed frontend files pass ESLint; optimized production build passed.
- Migration drift and whitespace checks passed. Both origin/main branches match
  the feature branches' base; no unrelated incoming changes.
- Source repeats/corrections, manual assignments, permissions/site isolation and DR
  behavior are covered by the finance regression. Historical source and ledger
  totals agree; pending local exceptions are documented in SPAIN_MIGRATION_AUDIT_20261116.md.

## Production publication

Target Railway project Beness_analytics, production. Backend repository
jlbrugnoni/beness_analytics_backend and frontend jlbrugnoni/beness_analytics_frontend
are deployed from main. Do not use another project's directory linkage.
Before release backend is 7b6b7a2, frontend 6d9ac63.

Create a production volume snapshot before push. Snapshot label: Before Spain
Finance V2 2026-11-16. Backup ID: 7f104cd9-c6b6-4656-ae1b-b508e4ad1c34.
This is a Railway volume snapshot, not a rehearsed PostgreSQL restore.

Commit only source, tests and handover documents; exclude exports/, private reports,
local databases, credentials and QA grants/configuration. Push the feature branch,
merge into main and push main. Backend Procfile applies migrations before Gunicorn;
0022_mindbody_assignments adds two tables and a company/code constraint, without
rewriting existing finance/Analytics transactions. Verify migration/startup logs,
Railway SUCCESS for both exact commits, public frontend and protected API routes.

## Production setup and owner smoke tests

Use the existing Spain Analytics site/studio, not local QA identities. Configure or
verify one active finance company Bewellness Group SL (ES/EUR), Estepona, Caixa bank
account and a cash account. Keep cash baseline unknown until evidenced. Do not
copy the local database. Preserve current DR configuration and role assignments.

In Finance configuration initialize Spain Mindbody mappings against Estepona:
Beness Pilates Estepona; Efectivo -> cash; Tarjeta de crédito (Visa/MC-No Auth) ->
card terminal. Preserve any existing customized rules. Configure terminal369092994
for Estepona/card terminal. Caixa settles full card amounts; separately charged and
returned terminal fees remain separate records. Initialize/import the shared expense
catalog through the existing catalog UI and set the agreed full-deposit policy.

Existing completed Analytics Mindbody sales supply expected income automatically;
no second finance sales upload is needed. Verify October2026 sales/closures, open a
sale/payment dialog, verify protected source facts and authorized review/reopen.
Preview Caixa Sep–Oct and the Spain historical workbook, select Estepona as blank
studio default, inspect overlap decisions before posting. Do not import overlapping
sources blindly. Verify manual cash receipt goes to the cash account/closure day;
cash deposited into bank is an internal movement and does not create a second sale.
Check a representative DR day as well. User production permissions remain unchanged.

## Known pending work

Unclassified historical expenses/missing dates and genuine duplicate ambiguities
remain visible for operational review. Negative/refund sales are held pending and
excluded; a real refund source example is still needed before full refund support
can be certified. A clean historical review queue is not a code deployment gate.

## Recovery

For an application regression, redeploy the previous successful backend/frontend
commits listed above. Migration0022 is additive: leave its tables in place rather
than dropping assignment/audit data. Investigate failed deployments before retrying.
Do not reset production financial data. If database recovery is required, stop writes
and obtain explicit recovery authorization, considering all writes since snapshot.
