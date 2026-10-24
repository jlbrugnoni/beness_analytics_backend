# Phase 2.1 accounts and terminals delivery

Date: 2026-10-24. Implemented and validated; client acceptance pending.
Both repositories: feature/finance-phase-2. Phase 2 as a whole is not complete.

## What I did

- Added Finance -> Financial configuration with editable companies, accounts,
  terminal-to-studio/payment-type mappings and active/inactive status in EN/ES.
- Added reference opening balance/date and statement-expectation fields.
  Unknown balances are distinct from zero. Dates mean start of day.
- Converted company/account APIs to revision-aware writes and added terminal
  CRUD plus scoped configuration options. GET access remains finance-gated;
  account/terminal data additionally requires full bank account capability.
  Writes require Manage financial configuration. Company editing and account
  creation require site-wide scope; a partial-studio grant cannot widen access.
- Retained company/account ownership, currency and cross-site integrity. Terminal
  mappings require a bank account and a participating studio of the same site.
  Account ownership/currency and terminal account cannot be reassigned. Multiple
  currencies per company/account conversion are outside this delivery.
- Reject duplicate terminal identifiers within an account. Different account
  contexts remain separate. Preserve identifiers as text.
- Stored config audit actor/time/before/after atomically. Updates require
  expected_revision; stale/missing revisions return 409. PostgreSQL row locks
  serialize competing writes. Hard deletion is disabled; deactivate instead.
  Technical Django admin is now read-only for Company/Account/Terminal so normal
  configuration edits use the audited UI/API path. Audit is technical-admin-only.
- Recorded eight DR terminals, the long-standing 3.5%/5% rates, and savings
  baseline/expected-balance policy in INITIAL_CONFIGURATION.md and discovery.

## Preview and boundaries

Local isolated SQLite QA only: http://127.0.0.1:3037/finance/configuration.
Backend http://127.0.0.1:8027. Use the same temporary review login supplied in chat.
The review user now has settings/account grants and site-wide QA DO scope.
The restricted viewer remains restricted. No real user grants changed.

Preview contains QA financial company, two Dominican account examples, the
0.00 DOP savings baseline on 2026-01-01, and all eight supplied terminal mappings.
These are temporary QA setup records, not migration data or production seeds.

Categories/subcategories, sensitive category flags, source mappings, fee/tax
configuration and dates remain Phases 2.2–2.4. Only terminal payment-type mappings
exist here. No fees are calculated, bank files imported, transfers processed,
expected balances calculated or results produced. Statement expectation is stored
now; import/completeness behavior is implemented in its later phase. No historical
rows are restated by this delivery. No production push/merge/deployment occurred.

## What you should test

1. Sign in again or refresh, then open Finance -> Financial configuration.
2. Accounts: verify both labels. Savings should show 0.00 DOP dated 2026-01-01
   and no statements expected. Operating opening balance should remain Unknown.
3. Terminals: compare all eight identifiers, studios and payment types against
   INITIAL_CONFIGURATION.md. No Arroyo Hondo recurring mapping is invented.
4. Edit an account label or terminal studio/type; save, refresh and verify it
   persists. Restore the intended mapping after testing.
5. Deactivate and reactivate a test terminal; the record remains visible with
   changed status. Try adding its identifier again in the same account: reject.
6. Clear only the balance or only its date and save: reject; neither field changes.
7. Open an existing record in two tabs. Save one then save the older form: show
   reload/conflict and preserve the first saved version.
8. Check EN/ES labels and existing screens. No report upload is expected yet.

## Validation and release

- 52 focused tests passed on isolated SQLite before final locking/admin refinements.
- 133 tests passed on isolated PostgreSQL 16 after refinements: 52 finance/access/
  configuration tests plus 81 existing analytics/purchase/import regressions.
- Django check and migration consistency check passed.
- Frontend lint/production build passed with existing unrelated warnings.
- Browser QA: companies/accounts/eight mappings render; account rename/save/
  restore persists; terminal deactivate/save/restore works. Account screenshot
  inspected at the normal preview size.

New migration: finance.0002_account_opening_balance_account_opening_balance_date_and_more.
Apply it before serving this backend, including when feature visibility is off.
Phase 1's deployment order and default-disabled feature policy still apply.
Only the isolated temporary QA database was migrated during implementation.
No raw financial reports or credentials are committed. The unrelated exports/
folder remains untouched. No external review agent was used.

Next subphase: 2.2 editable categories/subcategories and inherited sensitivity.
