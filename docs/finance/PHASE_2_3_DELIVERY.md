# Phase 2.3 source mappings delivery

Date: 2026-10-24. Implemented, validated and accepted by the client (D-039: "it looks good").
Both repositories: feature/finance-phase-2. Phase 2.4 remains future work.

## What I did

- Recorded Q-009 answers in D-037–038 and BR-045–048. The approved DR default
  is debit -> Link, credit -> Cierre with review, cash -> cash, transfer -> transfer.
  Recurring credit payments need an individual manual channel correction.
- Added editable company/source-field/value aliases for Alegra cost centers,
  price lists and payment methods, Mindbody studios/methods, and historical
  table studios/methods. These remain separate source namespaces.
- Map to a studio or financial channel, leave explicitly for review, or mark a
  price-list label neutral. Normalize Unicode/case/whitespace for exact matching;
  do not remove accents, fuzzy-match labels or infer missing values.
- Added Source mappings in Financial configuration, with EN/ES labels, add/edit/
  deactivate, active/review hints, and existing operational Mindbody method-name
  suggestions scoped to the company's site. This does not rename operational
  PaymentMethod, Studio or SaleLine records.
- Added an explicit Dominican setup action. A settings manager selects the
  existing three studios for Bella Vista, Piantini, Arroyo Hondo. It adds 11
  missing aliases: 6 studio labels, General neutral, 4 payment labels. Repeated
  setup preserves all existing target/review/active edits and creates no duplicates.
- Added an interpretation helper and Test mappings area. Cost center is primary;
  a price-list disagreement is a warning. Missing cost center does not fall back
  to the price list. General is intrinsically neutral even without an active alias.
- Preview can apply manual studio/channel choices. They take precedence while
  source labels, source suggestions, rule IDs/revisions and warnings remain in
  evidence. An explicit manual decision resolves that assignment's review need;
  warnings describing the source remain visible. Explicit manual clearing via
  API produces an unassigned review outcome; absence means use the rules.
- Writes, setup and preview require company-wide financial settings access.
  Reads follow finance/money/company scope. A studio-limited reader cannot see
  another studio's mapped alias. Bank-account and sensitive-detail grants are
  not required for this non-transaction configuration surface.
- Added atomic audit, revisions/stale-save protection, company-first locks,
  immutable source identity/company, and no hard deletion. Technical admin is
  read-only. Moving a company with mappings to another site is blocked.

## Boundaries

This phase configures/tests source interpretation. Preview POST does not save a
financial movement, manual correction, reconciliation or import. The helper is
not wired into existing operational uploads or a finance importer yet. No real
reports, invoice/customer rows or financial movements were imported.

Actual per-record manual editing/history and preserving those decisions across
imports are later phases. Fees, tax defaults, date/settlement rules, allocations,
expected balances and results are not calculated by source mappings. A channel
of transfer on a sale is not the internal-bank-movement classification.

Spain's initial channels are card terminal and cash. The exact exported Mindbody
labels remain unspecified, so no Spain aliases are guessed or seeded. The editor
supports selecting/typing those labels later; future recurring/transfer/link
configuration is possible without implying present use. Existing site-scoped
method names are suggestions when available, not guessed mapping decisions.

## API

- /api/finance/source-mappings/: scoped GET/POST, GET/PUT/PATCH detail; optional
  company ID filter. Delete unavailable. Identity fields are immutable; add a
  new alias and deactivate the old one when a reported label changes.
- /api/finance/companies/{id}/initialize-mappings/: POST expected_revision and
  studios dict with Bella Vista, Piantini, Arroyo Hondo -> selected studio IDs.
  Active DO company, three distinct same-site studios, settings/scope required.
  Adds missing records only; returns company, created, preserved. Complete
  repeated setup is a no-op even when recovering with an older company revision.
- /api/finance/mapping-preview/: POST company, source (alegra/mindbody/historical),
  source-specific labels and optional manual_studio/manual_channel. Returns
  assignments, origins, review reasons, source warnings and rule/version evidence.
  No account data or imported financial records are returned.
- configuration-options adds scoped mindbody_payment_methods metadata.

## Local QA and what you should test

Preview: http://127.0.0.1:3037/finance/configuration -> Source mappings.
Use finance-review@example.test with the same temporary QA password supplied in
chat. Refresh/sign in again if necessary. QA financial company has the 11
Dominican defaults linked to its test studios. QA spain company is an empty
Spain example; it has no invented Mindbody aliases. Only temporary QA user
scope was expanded to the synthetic Spain site. No real user permissions changed.

1. Inspect the four payment aliases: Tarjeta débito -> Link; Tarjeta crédito ->
   Cierre with Review required; Efectivo -> Cash; Transferencia -> Bank transfer.
2. Open Test mappings. Enter Bella Vista / General / Tarjeta crédito. Run test:
   Bella Vista and Cierre, with review required. Choose Recurring payments in
   Manual channel and run again: channel becomes recurring with Manual origin.
   The test saves no actual correction; original source warning remains visible.
3. Select Use mapping rules again, then Tarjeta débito: Link should be resolved.
   Efectivo and Transferencia should resolve directly when the studio is known.
4. Cost center Bella Vista plus price list Piantini: keep Bella Vista and show
   a conflict warning. Empty cost center plus Piantini: studio stays unassigned.
   General must not assign a studio or create a conflict on its own.
5. Add an unknown label to the test: leave unresolved for review. Add/deactivate
   an alias via the editor and check its effect; restore intended defaults after
   testing. A case/whitespace-equivalent duplicate in the same source field fails.
6. Edit a mapping in two tabs; the stale form must request reload. Repeating
   Dominican setup must preserve existing edits/inactive flags.
7. Select QA spain company: confirm the card/cash guidance and empty aliases.
   Exact Mindbody labels can be entered later. Do not use invented examples as
   real mappings. No extra recurring/transfer alias should appear automatically.
8. Check EN/ES labels and previous company/account/terminal/category screens.

## Validation and release

- 17 focused mapping tests passed on isolated SQLite.
- 170 tests passed on isolated PostgreSQL 16: 89 finance/access/configuration/
  mapping tests and 81 existing analytics/purchase/import regressions.
- Django check and migration consistency check passed.
- Frontend lint and production build passed with existing unrelated warnings.
- Browser QA: explicit three-studio setup, 11 aliases, Cierre review flag,
  manual recurring preview, edit/deactivate/restore a mapping. Screenshot of
  source label/manual choice/resolved result inspected at normal preview size.
- Preview runs created no financial records or configuration audit entries.

Migration: finance.0004_sourcemapping_and_more. Apply before serving the new
backend, even with finance visibility disabled. Previous additive migration and
compatible backend/frontend release order still apply. Only temporary QA/test
databases were migrated. No raw reports or credentials are committed. Unrelated
exports/ remains untouched. No external review agent was used.

No finance changes pushed, merged or deployed to production. Phase 2.3 accepted (D-039). Next: Phase 2.4 discovery and dated
fees/settlement/tax configuration.

Phase 2.3 implementation checkpoints: backend `0511e8a`, frontend `040f394`.
