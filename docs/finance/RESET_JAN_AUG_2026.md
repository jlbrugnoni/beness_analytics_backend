# Fresh DR supervised baseline: January–August2026

Date2026-10-28. Explicit owner request: delete current local finance test records,
re-import a supervised migration workbook covering2026-01-01 through2026-08-31,
compare months, then import routine September bank/Alegra reports and complete
manual assignments/entries until September agrees with Excel.

## Scope and backup

Reset applies only to the persistent local QA finance database at
/Users/joseluisbrugnoni/Beness_analytics/.local-finance/finance.sqlite3.
No production database, source spreadsheet outside the app or analytics data changed.
Companies, accounts, studios, terminals, categories, mappings, fees/tax/timing rules,
configuration/access history, users/groups/permissions and all other application
records were preserved. Finance transaction/import audit/check history was intentionally
cleared with its test records; the complete original dataset remains in the backup.

Private evidence and full pre-reset database:
/Users/joseluisbrugnoni/Beness_analytics/.local-backups/before-january-august-reset-20261028T165016Z/.
Includes backup.sqlite3, rehearsal.sqlite3, rehearsal-result.json, reset-result.json
and the reset script. Private directory0700/files0600; do not commit or export them.
Original schema is before0019; use a compatible checkout/settings if restoring.
A restore over a new baseline would discard new work and requires a separately
scoped owner instruction and a fresh backup of that new work.

Servers were stopped before backup/reset. A consistent SQLite backup was first
restored/rehearsed, then working rows were compared against that backup before any
reset mutation. Both runs applied0019, emptied24 finance import/transaction/check
tables in an atomic transaction and passed database integrity/foreign-key checks.
All55 non-target application/configuration tables had identical full-row hashes
before/after, excluding only the intentional django_migrations addition. No sequence
reset: old IDs are not reused just to make the next preview number start at1.

Removed612 money movements/classifications,1,214 invoices,1,219 payment receipts,
9 closure checks/11 events and their related imports, source rows, decisions and
financial audit events. These are old acceptance-fixture counts, not new baseline data.
Earlier acceptance/audit documents describe that previous dataset; do not use their
pending counts or September totals as the new dataset's current status.

## Explicit supervised migration policy (D-090)

MigrationImportBatch.supervised is stored with the uploaded source; existing batches
and API uploads that omit it default to false. The historical upload UI offers
This workbook has been supervised and reviewed, selected by default for the owner's
supervised baseline. History displays a Supervised baseline badge. Copying an
unposted preview to another company preserves the declaration but resolves that
company's own mappings; it does not blindly approve unknown foreign assignments.
The declaration is not editable after upload and does not retroactively rewrite
previously imported/edited records.

- Historical bank and actual cash income/expense assignments with all required
  configured fields are Reviewed, even without an Ingresos checkbox or with a false
  legacy Debitos checkbox. Required completion rules still apply.
- Historical Alegra invoices retain original source/mapping evidence and warnings.
  Resolved studio/method assignments are accepted without redundant ambiguity review.
  Genuine cost-center/price-list studio conflict and unresolved mappings stay reviewable.
- Historical transaction payments retain facts and invoice-link validation. Resolved
  payment methods no longer need redundant ambiguity review. Unknown methods/studios,
  invoice mismatch/cancellation/overpayment and source conflicts are not waived.
- Routine bank/Alegra reports retain normal review rules. Source changes still need
  explicit review. Reused records retain the supervised classifications.
- Reviewed is classification acceptance, not matched-to-invoice reconciliation,
  certified account balance, daily closure Checked or month closure. New checks start
  empty and the owner can compare/check the baseline month by month.

No Excel columns/checkboxes need to be added solely to declare supervision. The
selected destination account and separate actual cash migration still determine
origin; supervision is not evidence that every workbook row came through the bank.
Invalid dates/amounts/duplicates are not made valid by the declaration.

## User import sequence

1. Initial setup, choose the intended existing DR company (currently QA financial
   company). Finance navigation now carries the selected company into this page.
2. Upload the Jan1–Aug31 supervised workbook, leaving the supervised option checked.
   Verify source coverage/totals and all required sheets. Reading creates a preview;
   it does not by itself populate the ledger.
3. Post the selected bank rows, actual cash receipts and both Alegra sheets using
   the existing Bank/Alegra/Cash sections. Keep cash entries out of the bank import.
   Historical expenses with unknown origin retain the previously agreed bank default.
4. Inspect Reviewed status and correct actual unresolved mappings. Compare January
   through August month by month with the supervised document. Retain legitimate
   manual entries; do not create balancing receipts to force totals.
5. Upload routine September Popular CSV (debit+credit), Alegra invoices CSV and
   transactions XLSX. Invoices then payments is convenient; either order is supported.
   Use the actual overlapping reports to check occurrence reuse and classification
   preservation, then register real cash/manual items and complete September.

Owner cutoff is now settled: historical throughAug31, routine fromSep1. Launch-group
intentions, full-period acceptance and production setup/restore/release remain open.
This reset is an agreed local validation baseline, not a production cutover.

## Verification

340 PostgreSQL finance tests passed, including7 new supervised bank/cash/Alegra
cases. Changed frontend lint, optimized build and migration drift passed. API/DB reset
integrity and preservation evidence is in the private manifests. Browser confirms the
correct company, empty migration history and checked supervision declaration; no
replacement workbook was uploaded or posted by the agent. Local backend8027 and
frontend3037 restarted and left running. No merge/push/deployment or grant changes.
