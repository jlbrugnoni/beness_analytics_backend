# Beness Dominicana configuration package

Date: 2026-10-30. Branch: `feature/finance-module-v1.2` (backend and frontend).
Client request: carry the V1.2 permission changes and current Dominican financial
configuration together, under a single finance company named **Beness Dominicana**.

## Included configuration

The reviewed database settings were exported to
`finance/configuration_presets/beness_dominicana.json` with these counts:

| Configuration | Records |
| --- | ---: |
| Company: Beness Dominicana, DO / DOP | 1 |
| Accounts: Popular operating, Popular savings, general cash | 3 |
| Terminal → account/studio/channel mappings | 9 |
| Categories and subcategories | 56 |
| Alegra cost-center, price-list and payment-method mappings | 11 |
| Fee policies | 3 |
| Settlement timing policies | 3 |
| Sales tax profile | 1 |

Preserves source configuration values, including the savings reference balance of
DOP 0 on 2026-01-01; operating/cash reference balances remain unknown. Card-terminal
and recurring withholding are 3.5%, link withholding is 5%; no sales tax applies.
The nine terminals include the currently configured Arroyo Hondo recurring terminal
39618800005, in addition to the original eight-terminal list.

The source was local QA company 1 (the working Dominican configuration). Its
company name is replaced in the package only. Test companies, QA-only studios,
`Posting QA - Popular (DOP)` and its configuration are excluded. No local records
are renamed, reassigned or removed by preparing the package.

The package contains no invoices, receipts, bank/cash movements, classifications,
closures, import history, original reports, customer data, users, access grants,
credentials, database IDs, or account transaction balances. Opening reference
balances are configuration, not transaction history.

## Installation during deployment

This is an explicit deployment step, not a Django data migration or automatic
startup action. First deploy code and run normal schema migrations. Back up the
destination database and pause configuration edits during installation. Identify the destination's existing Dominican Republic
`Site` and the active superuser who will be recorded as the audit actor. Do not
use local QA IDs on production.

Run with the deployment environment and its configured database:

```sh
python manage.py install_beness_dominicana --site SITE_ID --actor SUPERUSER_ID
```

The command runs the complete installation within a rolled-back transaction and
prints created/unchanged counts. It saves no settings until explicitly applied:

```sh
python manage.py install_beness_dominicana --site SITE_ID --actor SUPERUSER_ID --apply
```

It requires the destination's existing studios, named exactly:

- Beness Pilates - Bella Vista
- Beness Pilates - Piantini
- Beness Pilates - Arroyo Hondo

Names are resolved within the selected DO site. Missing/ambiguous names stop the
installation. No analytics sites/studios are created or modified. Resolve name
mismatches before applying; do not duplicate existing studios to satisfy the seed.

The command creates only Beness Dominicana. It does not merge/rename other
companies or change any of their financial records. If production already has a
finance company with Dominican data under another name, review that situation
before installing a second company; do not use this as a company-merging tool.

Existing matching settings are reused; conflicts stop the whole transaction,
without overwriting or deleting anything. Repeating the command after a successful
installation creates no duplicates or extra audit records. Existing extra settings
are left intact. New settings receive configuration audit entries with the chosen
actor and the `beness_dominicana/v1` preset marker. Invalid settings or audit failure
roll back the entire installation. Settings remain editable through the normal UI.
Future UI changes do not automatically rewrite the checked-in baseline; a later
rerun will report differences instead of reverting those edits.

The package does not enable `FINANCE_ENABLED` or assign financial permissions.
Those remain explicit deployment/user administration tasks.

## Acceptance

1. Review the dry-run counts and studio names before applying to the destination.
2. Under Finance configuration, select Beness Dominicana and verify the three
   accounts, terminal assignments, categories, mappings and policy percentages.
3. Run the installer again: all 87 settings should be unchanged.
4. Begin the supervised migration/new-report workflow separately. The package
   must not introduce local QA transactions or users into production.

Production installation has not been performed. Existing local finance data is
untouched. The permission changes remain documented in V1_2_PERMISSION_ADMINISTRATION.md.


## Validation evidence

The complete finance PostgreSQL suite passed: 393 tests, including seven new preset
installer tests. These verify dry-run rollback, portable studio references, exact
configuration counts/values, repeat installation without duplicates, preservation of
existing movements, conflict rejection, missing-studio/wrong-country failure,
audit/late-validation rollback, active-superuser authorization and command defaults.
Tests used the disposable PostgreSQL database; no production configuration was applied.
