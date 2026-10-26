# Persistent local finance test runtime

Updated 2026-10-26 after the client restarted the Mac.

Frontend: http://127.0.0.1:3037/loginPage
Backend: http://127.0.0.1:8027

The former /private/tmp/finance-phase1-qa.sqlite3 database and temporary settings
were removed by the restart. Do not recreate working user datasets in /private/tmp.
Use that directory only for disposable test fixtures/databases.

Current working data and settings live outside Git under:

- /Users/joseluisbrugnoni/Beness_analytics/.local-finance/finance.sqlite3
- /Users/joseluisbrugnoni/Beness_analytics/.local-finance/finance_local_settings.py
- /Users/joseluisbrugnoni/Beness_analytics/.local-finance/start.sh

To start both services after a restart:

```sh
/Users/joseluisbrugnoni/Beness_analytics/.local-finance/start.sh
```

The launcher starts only missing listeners on8027/3037, binds localhost and writes
private logs in the same runtime folder. Syntax checked; both services were started
directly and their login/finance/frontend HTTP responses verified200. The launcher
does not migrate, seed, overwrite, restore or reset data.

Backend uses the existing project virtualenv, PYTHONPATH pointing to .local-finance,
DJANGO_SETTINGS_MODULE=finance_local_settings and PGHOST empty. Settings override the
database explicitly to the persistent local SQLite path and enable finance. Frontend
uses NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8027. Normal .env and db.sqlite3 are unchanged.

## Recovery scope

Restored a new working copy from the latest saved source snapshot:
.local-backups/before-alegra-workbook-20261026T133428/database.sqlite3. Backup remains
unchanged; SQLite integrity verified and migration0016 applied to the working copy.
Recovery includes322 bank movements, both workbook previews6/8, configuration and
existing access. It predates the later Alegra tests: no FinancialSale/FinancialReceipt
records are present. Do not claim those later test imports or edits were recovered.
Recreated reviewable Alegra previews from workbook8 through the normal prepare action;
no automatic financial posting. Client needs to repeat the Alegra invoice/payment
imports before the routine September overlap acceptance exercise. No reset performed.

The shared existing local QA account remains finance-review@example.test with the
same password previously supplied in chat. Its saved legacy test password hash was
verified against that password, then upgraded to the standard Django hash. No password
change, role expansion or permission changes. Other users were not modified.

Keep the working database and source blobs backed up before destructive maintenance.
Do not commit these databases, logs, source workbooks or local runtime settings.
