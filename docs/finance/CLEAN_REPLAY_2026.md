# Clean local finance replay — 2026-10-28

D-092: owner accepts improving rejected invoice visibility and backing up/resetting
finance transactions/import history before replaying January–August and September.
Business configuration, users, permissions and analytics must remain intact.

## Import review delivery

Daily Upload reports and historical/advanced invoice processing now offer All invoices /
Rejected invoices plus invoice-number search. Counts summarize the full import while
pagination applies to the selected filter. Each invoice shows validation messages and
exact source rows. Missing invoice/item totals are explained explicitly, not presented
as zero or derived from payment amounts. Original source detail also shows source rows.

Payments awaiting an invoice now distinguish no known invoice from an invoice rejected
in a posted report, showing missing-total/invalid-source explanation, original filename
and source rows. This is diagnostic presentation; source validation, identity, financial
values, permissions and import decisions remain unchanged. A new valid invoice report
can create a previously rejected invoice and automatically reassess existing payments;
no payment reupload is needed. Split-payment/group and name/amount review rules remain.

B0200000880 was verified against the existing source: invoice row1009 has blank invoice
and item totals; payment1037/5,440.00 exists. Browser verified rejected-row diagnostics
before reset. Available named Alegra exports cover the prior September exercise; no
corrected February report was supplied. Missing financial source values were not filled
or changed. Owner must supply verified totals/corrected workbook or fresh invoice report.
Reset itself does not solve the114 incomplete invoices.

## Backup and reset

Only .local-finance/finance.sqlite3 was reset, with servers stopped. Consistent full
backup and rehearsal at private directory:
.local-backups/before-clean-replay-reset-20261028T210216Z/
Includes backup.sqlite3, rehearsal.sqlite3, reset_finance_clean_replay.py,
rehearsal-result.json and reset-result.json. Private0700 directory/0600 files. No
production changes or source workbook changes. Restore over later work requires a
new explicit request and backup; do not overwrite a replay automatically.

Reset rehearsed on copy; compared complete working-table hashes to backup before
applying. Cleared24 finance transaction/import/check tables; removed2,351 movements/
classifications,4,881 invoices,4,984 payments, their import/source/decision/events.
No closure checks existed.55 non-target application tables remained byte-for-byte
identical by full-row hash: accounts (bank/cash), companies, terminals, categories,
mappings/fees/rules, configuration/access audit, users/groups/permissions and analytics.
SQLite integrity/FK checks passed. Schema remains finance0020. IDs were not resequenced.

## Replay and acceptance

1. Initial setup → existing DR company. Upload corrected Jan1–Aug31 supervised
   workbook with supervision checked. Prepare/post bank, actual cash and both Alegra
   sections; inspect rejected invoices before importing. Do not recreate configuration.
2. Confirm January–August monthly totals against Excel. Correct genuine missing
   source values; preserve rejection rather than manufacture an invoice total.
3. Routine September1–15 bank/invoices/payments, then14–30 overlap. Confirm occurrence
   reuse, preserved assignments, invoice-payment comparisons and review workflow.
4. Register legitimate manual cash income/expenses; compare closures and check/reopen.

352 PostgreSQL finance regression tests passed. New tests cover rejected-only search,
source rows, missing-total diagnostics without mutation, valid rows posting alongside
rejections, and a corrected report linking existing split payments without duplicates.
Frontend changed-file lint/production build passed. Database backup/reset verification
passed; local backend8027/frontend3037 restarted. Client replay acceptance pending.
No merge, push, deployment, permission change or automatic exception acceptance.
