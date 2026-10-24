# Phase 1 foundation and access delivery

Date: 2026-10-24. Status: implemented and validated; client acceptance pending.
Branch in both repositories: `feature/finance-phase-1`.
Tested implementation commits: backend `4c0bf21`, frontend `630739e`.

## What I did

- Added Django `finance`, its feature flag, and additive migrations. Company and
  Account are financial ownership/configuration foundations; AccessChange records
  actor/time and before/after access changes. No real companies/accounts were seeded.
- Added nine explicit finance capabilities to existing group/user profiles.
  Defaults are false. Existing operational Admin behavior remains; ordinary Admin
  membership does not grant finance actions. Django superusers retain technical
  access when the feature is enabled.
- Financial entry requires View money + View finance + enabled feature. Company
  results obey existing location scopes. Partial studio scope cannot see full
  shared/unassigned accounts. Full-account viewing is a separate capability.
- Added Settings -> Group permissions, finance switches in user add/edit, and
  effective permissions with their group/direct sources. Multiple group grants
  combine by OR. Site/studio selectors load all pagination pages.
- Added protected Finance navigation/landing with scoped companies and English/
  Spanish labels. The page explains which functions are not available yet.
- Combined user identity/groups/profile saving atomically. New forms submit an
  `access_profile` object within the existing users endpoint. A stale profile
  revision returns 409 and rolls back the complete change. Legacy separate profile
  endpoints remain compatible, with optional expected_revision checks.
- Added permission-change audit and revision increments for API profile edits,
  API user group/status changes, and Django admin profile edits. Audit failures
  roll back the permission change. Prevented non-superuser API promotion to
  superuser and protected superuser profiles from ordinary user managers.
- Added shared-account studio validation, including reverse membership changes,
  and admin/model validation against moving an account/company across ownership.

## Implemented surface

| Surface | Behavior |
| --- | --- |
| `/api/finance/` | Authenticated finance-gated API root |
| `/api/finance/overview/` | Foundation status and scoped company list |
| `/api/finance/companies/` and detail | Read-only scoped company metadata |
| `/api/finance/accounts/` and detail | Read-only metadata requiring full-account capability and complete participating-studio scope |
| `/api/data/me/permissions/` | Existing payload plus finance state and capability sources |
| `/api/data/groups/` | Group names plus capability defaults/profile IDs |
| Existing group/user access profile endpoints | Additional finance flags, revisions, user effective-access explanation, audited writes |
| Existing POST/PUT users endpoint | Optional nested access_profile saved atomically with user/groups |
| `/settings/groups` | Edit existing group capabilities; reload on concurrent conflict |
| User add/edit/info | Direct financial grants and inherited/effective access explanation |
| `/finance` | Protected finance landing; scoped companies only |

Location semantics match the existing system: selected studios restrict ordinary
users; site selection applies when no studios are selected. Admin retains existing
global location scope only after receiving explicit finance grants; superuser
is the technical exception. Sensitive capability never grants wider location scope.

## Boundary of this delivery

This phase implements access foundations, not financial processing. Terminals,
category CRUD/sensitive-category flags, fee/tax rules, imports/migration, manual
financial movements, reconciliation, results, and salary-row redaction are later
phase work. The sensitive-detail capability/helper exists now; no salary/detail
endpoint exists yet. Do not report transaction privacy acceptance A-28 as complete.
Closing is reserved for future use; no month-lock workflow is implemented.

Company/account configuration currently uses the technical Django admin; normal
configuration UI and write APIs belong to Phase 2. Finance read APIs deliberately
reject writes. No source reports or personal financial records were imported.

## Validation

- 39 focused finance/access tests, plus 81 existing analytics/import/purchase
  regression tests: 120 total, passing on isolated PostgreSQL 16.
- Focused suite also verified on isolated SQLite before the final API-root case.
- Django system check and migration consistency check passed.
- Frontend lint and production build passed with existing unrelated warnings.
- Browser check with synthetic local data: sign-in, scoped Finance page, group
  selection/save, immediate navigation revocation, protected-route redirect, and
  restoration. Inspected layout at the browser's desktop and narrow panel sizes.
- Self-review only; no external review agent used.

Reproduce backend regression checks against an isolated test database:

```sh
python manage.py test finance analytics core_data.test_purchase_matching core_data.test_purchase_repair core_data.test_analytics_import_guards --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
```

Frontend checks: `npm run lint` and `npm run build`.

## What you should test

Use staging/local test users rather than changing real partners' grants while
learning the new permission editor.

1. Open Settings -> Group permissions as a user manager. Select an existing
   test group, enable View money and View finance, and save. Group members inherit
   those grants; their own switches can remain off.
2. Enable finance in the test environment. With the user's allowed site/studio
   set, Finance appears and shows only available companies. With no scope, no
   companies appear. No actual financial results should appear yet.
3. Remove the group's View finance permission when the member has no direct
   grant. Finance disappears after refreshed access; direct route access fails.
   A direct user grant remains effective even after the group grant is removed.
4. Open user add/edit/info. Check the new switches and inherited-source labels.
   An unchecked direct flag does not revoke inherited permission.
5. Load the same profile in two sessions. Save one, then save the stale other.
   It must request reload, without partially changing user/groups or redirecting
   away from the error.
6. Give a test user full-account view but only one studio in a shared account.
   Account detail must remain unavailable; sensitive capability does not bypass it.
7. Switch English/Spanish and check new labels. Existing dashboards/uploads should
   retain their previous behavior.

## Deployment and handoff

Not pushed, merged, or deployed. Existing local application DB and production data
were not migrated or modified. QA uses separate temporary databases and synthetic
users; temporary credentials and financial source files are not committed.

Apply `core_data.0020_groupaccessprofile_can_close_finance_periods_and_more` and
`finance.0001_initial` using `python manage.py migrate` in the intended test/release
environment before serving the new backend. This is necessary even with the
feature disabled, since access profiles gain new columns. Take the environment's
normal backup before migration. Do not run these against an unintended database.
Deploy the compatible backend before the new user/group frontend, so the nested
access_profile save contract is available. Verify access endpoints before enabling
the finance feature; the flag does not substitute for applying migrations.

`FINANCE_ENABLED=False` is the default and documented in `.env.example`.
Set true in staging/local only when ready to test. Existing ordinary groups/users
receive no financial permissions automatically. Grant them through the group/user
editor; real company/account setup remains explicit.

Rollback for visibility: disable the flag and serve a compatible frontend.
Retain additive tables/history. Do not reverse migrations containing imported
financial data as a visibility workaround. Production release remains a separate
client-authorized step.

Next: client acceptance of Phase 1, then Phase 2 editable company/accounts,
terminals, categories/sensitivity, mappings, and dated fee/tax configuration.
