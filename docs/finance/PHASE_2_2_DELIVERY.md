# Phase 2.2 editable categories delivery

Date: 2026-10-24. Implemented, validated and accepted by the client on 2026-10-24 (D-036).
Both repositories: feature/finance-phase-2. Phase 2.3–2.4 remain future work.

## What I did

- Recorded the four Q-008 answers in D-032–035 and BR-042–044.
- Added company-owned categories with one subcategory level, editable names,
  operating/extraordinary/review defaults, direct/shared-administration defaults,
  sensitivity and active flags, revisions and audit history.
- Added Categories in Finance -> Financial configuration, in English/Spanish.
  Root defaults are explicit; child defaults may inherit or override them.
  The editor shows the inherited value and explains inherited sensitivity.
- Added a repeat-safe Use starting catalog action for each empty company. It
  creates 10 categories and 45 subcategories from the accepted baseline. The
  extra Otros / Extraordinarios is included; invalid 1 / 1 is not seeded.
- Common initial categories carry permanent catalog codes across companies,
  supporting comparable analysis later. Renaming preserves codes/references;
  edits in one company do not propagate. Custom categories receive independent
  codes; copying/alignment of later custom catalogs is future work. There is
  no cross-company result engine in this phase.
- Baseline configuration lives in finance/catalog.py only as an initializer.
  Saved database records are authoritative and editable through the app; code
  edits are not required to rename, add or deactivate company categories.
  Child codes in the template are explicit permanent values; do not renumber
  them when changing display order or names in a future template version.
- Initialization is transactional and audited. Repeating completed initialization
  creates nothing and does not overwrite edits. A manually started catalog
  blocks initialization with 409 rather than merging or replacing its records.
- Category/company ownership and parent cannot be reassigned. Unicode/case/
  whitespace-normalized duplicate names are rejected within a company/parent.
  No hard deletion. An inactive parent makes children effectively inactive but
  retains their own flags/settings for later reactivation.
- Writes require site-wide financial settings access. Sensitive categories,
  sensitivity changes, and parents containing sensitive children additionally
  require sensitive-detail access. A child under a sensitive parent remains
  sensitive even if its own switch is off. Labels/settings remain readable
  within company scope; they contain no individual payment details.
- Updates require expected_revision. Children also require the current parent
  revision. Company-first locking serializes category/parent changes on
  PostgreSQL, and audit failures roll back changes.
- Protected moving a company to another site when it owns categories even if
  no accounts exist. Technical Django admin for categories is read-only; use
  the audited app/API for configuration writes.

## API

- GET/POST /api/finance/categories/; GET/PUT/PATCH detail. Optional company ID
  filter on list. Delete is unavailable. Reads follow finance view/money/scope;
  category taxonomy does not require bank-account visibility.
- POST /api/finance/companies/{id}/initialize-categories/ with expected_revision.
  Requires site-wide settings plus sensitive-detail access. Returns updated
  company and created count (55 first time, zero on repeated completed setup).
- Company read payload adds read-only category_catalog_version.
- Category payload includes stable catalog_code, parent/current revisions,
  own/effective sensitivity/active/default values, and server-computed edit hints.

## Accepted defaults

Personal is sensitive, as are Administracion / Sueldos administración and
Seguridad social administración. Administracion defaults shared administration;
other roots default direct. Ordinary costs are operating. Administracion /
Impuestos and Otros / Extraordinarios default extraordinary. Operacion /
Equipamiento, Bancos / Intereses and Bancos / Devoluciones require review.
Explicit historical studio assignments must be preserved by later migration;
these defaults cannot silently replace them.

These are configuration defaults, not calculated results. No bank/sales files,
financial movements, salary payments or actual expense rows were imported.
Transaction privacy across search/history/export/raw downloads remains future
processing work (BR-037/A-28); do not claim it complete from category flags alone.
No tax/fee calculation, administration allocation or restatement is performed.

## What you should test

Preview: http://127.0.0.1:3037/finance/configuration, Categories tab.
Use the temporary finance-review@example.test login already supplied. Sign in
again if its added QA sensitivity grant is not reflected. Passwords are not
committed in this repository. QA financial company and QA second company both
have the starting catalog so you can compare them. All are isolated local data.

1. Check all 10 root categories and the additional Otros / Extraordinarios.
2. Open a Personal subcategory: verify Sensitive (inherited), Use parent default
   and the explanation that its own unchecked flag does not remove protection.
   The two Administracion payroll/social-security children are sensitive too.
3. Check review defaults on Equipamiento/Intereses/Devoluciones, extraordinary
   Impuestos/Extraordinarios and shared-administration guidance on Administracion.
4. Rename an ordinary category or subcategory, save and refresh. It should persist
   and keep its children. Select the other company: its catalog remains unchanged.
5. Add a test category/subcategory. Try a duplicate name in the same parent with
   changed capitalization/spaces: reject. You can deactivate test records afterward.
6. Deactivate a parent and verify children are effectively inactive without being
   deleted; reactivate it to restore their effective state.
7. Open one category in two tabs; save one then try the older form. It must request
   reload. A parent changed in another tab also makes an old child form stale.
8. Optional privacy-editor check: finance-settings@example.test uses the same
   temporary QA password and has settings permission but no sensitive-detail or
   bank-account grant. Categories work; sensitive edits are disabled and ordinary
   edits are allowed. No real data or real user permissions are involved.
9. Check EN/ES labels. Existing companies/accounts/terminals should still work.

Company-wide setup is deliberate: studio-limited settings users can read their
company catalog but cannot change shared company definitions.

## Validation and release

- 153 tests passed on isolated PostgreSQL 16: 72 finance/access/config/category
  tests plus 81 existing analytics/purchase/import regressions.
- 20 category tests passed on isolated SQLite; the same 20 passed again on PostgreSQL after making template child
  codes explicit (no code values changed).
- Django system check and migration consistency check passed.
- Frontend lint/production build passed with existing unrelated warnings;
  final build also includes the inherited-select display and validation-message refinements.
- Browser QA: initialize both companies, display defaults, open/save inherited
  salary category, rename a root in one company, confirm the other is unchanged,
  and restore the original name. Duplicate creation stays in the form with a clear error.
  Restricted settings user can edit Servicios but cannot edit Personal or the
  Administracion parent with sensitive children.

New migration: finance.0003_company_category_catalog_version_category_and_more.
Apply before serving this backend even if finance visibility is off. Use the
existing additive migration/compatible release order from previous handoffs.
Only temporary QA/test databases were migrated. No production push, merge,
deployment or permission assignment was performed. No raw reports or credentials
are committed. Unrelated exports/ remains untouched. No external review agent.

Next: client acceptance of Phase 2.2, then Phase 2.3 source/payment/studio mappings.

Phase 2.2 implementation checkpoints: backend `3670958`, frontend `0b36d89`.
