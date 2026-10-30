# Category catalog recovery and CSV transfer

D-098 · 2026-10-30 · Client requested production recovery and local-to-production
catalog transfer, tested locally and committed directly to main.

## Workflow

Open Finance → Restore / transfer category catalog, or use the same button in
Finance configuration → Categories. The direct route is `/finance/category-catalog`.

1. Select the company explicitly (automatically selected only when one is visible).
2. Export its current CSV before making changes. The full catalog includes inactive
   rows, hierarchy, result/allocation defaults and privacy flags; no financial rows.
3. Choose Import CSV or Restore starting catalog.
4. Choose update/add while keeping other categories (default), or update/add and
   archive absent categories.
5. Preview added, updated, unchanged and archived rows. No settings are saved by
   preview. Apply requires the returned signed preview token.

For the requested transfer: export the working local catalog, open this screen on
production, select Beness Dominicana, upload that file, preview, then apply. The
browser-tested local file was downloaded as `finance-category-catalog-1.csv`.
No production data was modified during development/testing.

Restore uses the original starting catalog (10 roots/45 children), not a copy of
local customization. CSV transfer preserves all 56 current local entries. Neither
path deletes categories or removes their links to expenses. Archiving sets
`active=False`. Company accounts, terminals, mapping rules, transactions,
classifications and review statuses are not changed by this operation.

## Permissions and scope

Export, preview and apply require `can_import_finance_migration`, finance/money
access, `can_view_sensitive_finance`, and company-wide site authority. Individual
studio restrictions do not allow company-wide transfer. A settings manager without
migration permission cannot transfer catalogs. A migration user with the above
scope/privacy permissions can use the dedicated page without the separate settings
management permission. No new user grants or permission flags are introduced.
Ordinary per-category editing and the existing empty-catalog initializer retain
their existing permission policies.

## CSV contract

UTF-8 (Excel-compatible BOM supported), comma or semicolon delimiter, maximum
2 MB and 2,000 data rows. Header order may vary but these columns are required:

```csv
catalog_code,parent_code,name,default_treatment,default_allocation,sensitive,active
servicios,,Servicios,operating,direct,false,true
servicios-01,servicios,Electricidad,,,false,true
```

- Codes are unique, 1–64 characters, using letters/numbers/underscores/dots/hyphens.
  Preserve codes when renaming categories.
- Include every referenced parent as a root row. Only two levels are supported.
- Treatments: `operating`, `extraordinary`, `review`; children may leave blank to
  inherit. Allocation: `direct`, `administration`; children may inherit with blank.
- Boolean fields accept `true`/`false` or `1`/`0`.
- No local database IDs or company IDs are imported from the file. The selected
  destination company determines ownership.
- Formula-like names are escaped on export and unescaped on reimport, preventing
  executable spreadsheet cells while preserving their original text.

Match by company/catalog code first. If no code matches, reuse a manually created
category with the same normalized name and resolved parent; preserve its ID and
existing generated code. The preview displays its target code and the source code
in parentheses when different. Subsequent exports reflect destination codes.
Unmatched rows create new categories. Duplicate targets, duplicate codes/names,
reparenting, malformed rows and invalid values stop the whole operation. Never
silently reassign a category already linked to expenses.

## Integrity and recovery

Company/category locks serialize configuration edits. The signed preview binds the
actor, company, catalog state (including category revisions), normalized CSV rows,
source and merge/archive mode. Preview expires after one hour. Changes to any bound
value require a new preview (409). Applying another user's preview is rejected.

The actual model validation/audit path runs inside a rolled-back transaction for
preview. Apply repeats those checks and commits every change/audit atomically.
A validation/audit failure rolls back all changes. No partial catalog is left to
reset. Changed categories increment their revisions; changed company catalogs
increment company revision and set the catalog version (`beness-v1` for starting
restore, `csv-v1` for CSV). Identical retries after a fresh preview are no-ops.

## Production pagination correction

Finance category/configuration/mapping/policy and import-history loaders previously
followed the API's `next` URL directly. A TLS-terminating deployment may return an
HTTP/internal-origin URL after page 1. With 55 categories and page size 15, a browser
can block the second request and show the generic configuration error after the
initial catalog was successfully created. Reloading repeats the same failure.

Those loaders now use the existing `normalizeApiNextUrl` helper to keep the
configured backend origin while preserving path/query parameters. This is a
reproduced deployment failure mode matching the client's symptoms, not a confirmed
inspection of the live production response. No proxy trust/security settings were
changed and no production reset is needed for this failure mode.

## Validation evidence

- 407 finance tests passed on isolated PostgreSQL, including 14 new catalog tests:
  preview rollback, restore/retry, cross-company CSV round trip, default parity,
  merge/archive with preserved reviewed expense references, manual-name matching,
  stale/changed/other-actor previews, permissions/scopes, invalid CSV/hierarchy,
  audit rollback, spreadsheet formula escaping and inactive-company safeguards.
- Two frontend pagination regression tests passed, including 55 records across
  four pages with HTTP/internal-host next links and a configured HTTPS backend.
  Run: `node --test tests/financePagination.test.mjs`.
- Frontend build and targeted ESLint (including undefined-name checking) passed.
- Browser on the existing local QA database: exported CSV, uploaded it, previewed
  all 56 entries as unchanged and applied successfully. Company revision remained 4,
  configuration audit count remained 158, and the full category-row SHA-256 before/
  after was identical: `52f6e9d30e2db616903248fe64d1f4efe72510fb5fe72ac7fc1e42282faadf2a`.
- Local financial records and settings were preserved. Production acceptance remains
  to be performed after deploying both code changes. No schema migration is needed.
