# DR operational finance V1 — cutover and recovery runbook

Prepared2026-10-28 on feature/finance-phase-2. This is a reviewable release procedure;
it is not permission to merge, push, deploy, change working grants or reset data.
Spain and financial analytics remain separate releases.

## Decisions still needed from the owner

- Last historical-workbook date and first routine-report date. Overlaps are supported,
  but the source versions and intended coverage must be recorded.
- Existing launch groups and their intended view/import/edit/reconcile/settings
  capabilities. These are independent permissions, resolved through existing user/
  group grants and site/studio scope. No new production roles are assumed.
- Confirm actual company/site/studio/account/terminal mappings and opening balances.
  Local company1 is named QA financial company and includes a Posting QA account;
  those labels/IDs are not production configuration. Review terminal39618800005,
  which is configured locally in addition to the eight originally supplied terminals.
- Identify legitimate manually recorded entries versus disposable testing entries.
  Do not use a naming heuristic as authority to delete or copy financial data.

## Deployment facts verified from this repository

Backend Procfile runs `python manage.py migrate` before starting Gunicorn. Therefore
obtain and verify backups **before restarting/deploying the release**, not afterward.
Inspect the full migration plan against the actual deployed revision; do not assume
finance0018 is the only unapplied migration in a production database.

The backend uses PostgreSQL when PGHOST is configured, with POSTGRES_DB/PGDATABASE,
POSTGRES_USER/PGUSER, POSTGRES_PASSWORD/PGPASSWORD and PGPORT. Without PGHOST the
normal settings fall back to SQLite. Confirm the actual target engine/database using
server-side configuration without printing credentials. Never use local finance
settings or the local SQLite file as production settings/data.

FINANCE_ENABLED defaults to false. Existing money/finance/sensitive/account and scope
permissions still gate the feature when enabled. NEXT_PUBLIC_BACKEND_URL is the
frontend's build-time API destination; build it for the intended backend, never8027.
Financial import originals are stored as binary database fields, so the database
backup must retain them. Inventory any non-finance media/external files separately.

## A. Rehearse in a separate staging dataset

1. Record approved backend/frontend commits, runtime/dependency versions and the
   currently deployed revision. Use staging credentials and target DB identifiers.
2. Back up the target database before schema changes. For PostgreSQL use the hosting
   provider's verified snapshot or a full custom-format pg_dump, not a finance-only
   table export. Keep backup files/access private and record timestamps/checksums.
3. Restore into a newly provisioned isolated PostgreSQL database of compatible
   version. Never test a restore over the source/working database. Confirm integrity,
   migration state and application connectivity. Full original-file binary fields,
   assignments, import decisions, users/scopes and audit history must survive.
4. Review `python manage.py migrate --plan`, then apply migrations only to staging.
   Compare pre/post record counts and representative amounts, assignments, source
   file hashes, pending decisions and check history. New schema tables may appear;
   existing financial facts must not disappear or be reassigned.
5. Configure staging company/account/studio mappings using actual staging IDs.
   Keep original bank dates separate from operation dates and expense periods.
   Apply the agreed3.5% Cierre/recurring and5% Link policies; savings starts0.00 at
   2026-01-01 without expected statements. General cash does not expect statements.
6. Import the agreed historical document through normal migration workflows. Bank
   expenses default to the explicitly selected bank account; actual historical cash
   receipts use the designated cash migration. Review source/classification previews.
   Import both historical invoice/item and transaction/payment sheets through their
   supported workflows. Record counts/amounts by source and date, not just row totals.
7. Upload routine Popular CSV (both debits and credits), Alegra invoice/items CSV and
   transactions XLSX (Ingreso payments; Egreso not posted as customer income). The
   convenient sequence is invoices then transactions; the reverse is also supported
   and rehearsed. Bank upload is independent. Do not merge different account scopes.
8. Upload an overlapping report, then repeat the same reports. Review expected reused
   occurrences and legitimate changes; confirm no extra financial records, preserved
   assignments and no silent resolution of uncertain identities. New source changes
   must go through review. Do not overwrite original facts to remove conflicts.
9. Recreate the accepted daily cycle with actual evidence: bank/cash receipts, cash
   expense, operation dates, monthly expense period, internal/refund exclusions,
   closure check/reopen/recheck. Verify full-period coverage against the document.
10. Test intended existing group profiles and direct URLs, including a denied company/
    studio and denied sensitive detail. Finance viewers must not gain import/edit/
    reconcile/settings merely because they can view. Do not broaden permissions to
    make a test pass. Record owner approval of mappings/grants before production.

## B. Authorized production cutover

1. Obtain explicit release authorization and record accepted source coverage/cutoff,
   unresolved items, staging results and the owner-approved mapping/access matrix.
2. Arrange a short agreed import/configuration pause so a consistent pre-release
   backup and post-release inventory can be compared. Preserve the current release
   artifact and database migration inventory. Verify restore access before deployment.
3. Deploy the compatible backend/frontend and planned migrations using the actual
   environment. The Procfile can migrate automatically; do not start it before step2.
   Keep finance visibility limited to intended authorized users during verification.
4. Create/verify real configuration through the app and perform the approved initial
   import sequence. Do not copy the entire QA SQLite database, QA profiles or numeric
   foreign keys into the shared production database. Do not re-import historical cash
   as bank income or create manual balancing entries to hide incomplete coverage.
5. Verify login, API destination, feature flag, group/site/studio/sensitive scope,
   counts/amounts, preserved raw reports, overlap/repeat behavior and audit/check
   history. Record a real first-cycle result with the client before general launch.
6. Resume routine imports and document the exact first live report dates and any
   outstanding decisions. Never mark a full month reconciled solely because one day
   or one method balances. Running balances and hard month locks are not V1 promises.

## C. Recovery/rollback

For an isolated mistaken cash migration, first inspect the existing audited undo/
restore preview. Later edits/checked or reconciled records and overlaps can protect
entries. A source change or pending import uses its normal explicit review path.
Do not delete sources/history or repeat an import to repair an uncertain identity.

For a release incident, pause new finance writes through the approved operational
procedure and restrict finance visibility if required. Preserve new sources/audit
records and diagnose on a copy. A code rollback must be compatible with the already
applied schema; do not reverse/drop migrations as an automatic shortcut. If database
restore is genuinely required, obtain explicit scoped approval, account for all
post-backup writes and restore the whole compatible dataset using the validated
provider procedure. Do not discard newly entered business records silently.

After recovery repeat integrity, source/count/amount, assignment, access and history
checks, then obtain owner acceptance before resuming routine imports.

## D. Completed local rehearsal (limits explicit)

Private evidence directory:
`/Users/joseluisbrugnoni/Beness_analytics/.local-backups/dr-v1-restore-20261028T162036Z/`.
Directory permissions0700; database/manifest/script files0600. It contains sensitive
local application data and must not be committed, attached or copied to production.

A consistent backup of the persistent local SQLite DB was restored into a separate
SQLite DB. Integrity and foreign-key checks passed. All80 application tables matched
by row count and canonical full-row/schema digest, including hashes of binary import
originals. Eight read-only finance API responses matched exactly after restore:
options, income, expenses, invoices, monthly closures, review evidence, check history
and invoice import processing. Read verification used query_only. Original backup
was rechecked unchanged after scenarios.

Only the restored scenario copy received four synthetic money entries: internal
movement, refund, extraordinary income and cash expense. The three excluded credit
kinds left gross/fees/expected/actual monthly collection totals unchanged; retries
reused IDs, conflicting retries returned409. Expense retained August period with a
September transaction date; void preserved the record and audit event.

A second restored copy used a synthetic user/group for18 permission scenarios.
Viewer reads worked; edit/reopen were denied. Edit capability allowed the synthetic
operator edit; reconcile stayed denied. Revoking each required visibility capability
blocked comparison/history. Site removal and partial studio scope denied company
closures. A group reconcile grant permitted an audited reopen. Disabled finance and
inactive user denied access. Denied requests left money/classification/check/audit
records unchanged. No working profiles/groups/grants were modified.

Manifests: manifest.json and access-manifest.json. Rehearsal scripts are retained
privately alongside them. These local checks supplement the333-test PostgreSQL
regression suite; they are not a PostgreSQL dump/restore rehearsal, actual production
mapping approval or owner testing with real partner credentials. Those remain in
sectionsA/B and DR_OPERATIONAL_RELEASE.md.
