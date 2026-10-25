# Phase 2.4 fees, timing and sales-tax delivery

Date: 2026-10-24. Implemented and validated; client acceptance pending.
Both repositories remain on feature/finance-phase-2. No production deployment.

## What I did

- Recorded Q-010 answers as D-040–041 and BR-049–051. Caixa deposits arrive in
  full; its terminal fee and reimbursement are independent. The approximate
  EUR 36 charge and offer ending in 2027 remain notes. Exact amount, frequency
  and offer dates are unknown, not invented structured defaults.
- Added FeePolicy, SettlementPolicy and TaxProfile, migration
  finance.0005_taxprofile_settlementpolicy_feepolicy. Common fields: company,
  nullable baseline/start/end, notes, active, revision and audit history.
- Added GET/detail/POST/PUT/PATCH endpoints /api/finance/fee-policies/,
  settlement-policies/ and tax-profiles/. No hard-delete. Writes require
  finance visibility/money access, settings capability and full-site scope.
  Settings do not require bank-account or sensitive-payment permissions.
- Company/channel identity cannot change. Date ends are inclusive. Active rules
  of the same type/company/channel cannot overlap; tax rules are company-wide.
  Company-first locks serialize overlap checks/setup. Stale updates return 409;
  changes are audited. Technical admin is read-only. Any policy protects company
  site identity; a fee policy also protects currency identity.
- Added explicit /api/finance/policy-setup/. DO adds seven missing policies:
  3.5% Cierre, 3.5% recurring, 5% Link net deposits; three typical 24–48-hour
  timing rules with weekend delays; no-sales-tax profile. Spain adds two:
  full card deposit/reimbursement expected and 21% included sales tax.
  Baselines do not invent contract/legal start dates. Existing rules, including
  inactive/dated/customized ones, are preserved; a complete repeat creates none.
  Company revision is required if anything is missing and increments on setup.
- Added read-only /api/finance/policy-preview/ with company/date/channel/gross
  amount. It returns applicable IDs/revisions, estimated withheld fee/deposit,
  informational included tax, and typical timing. Unknown withholding/tax stays
  null with review. Unknown separate fee is separately displayed even when the
  full deposit is known. It creates no transaction, correction or audit record.
- Added EN/ES Fees, timing & tax tab, company selector, three editors, setup
  explanation, clear unknown-versus-zero fields and calculation preview.
  Conflicting/stale saves remain reviewable; reload refreshes parent data.

## Calculation boundaries

DR preview 100 DOP Cierre -> 3.50 withheld -> 96.50 deposit; Link -> 5.00 -> 95.00.
The preview rounds percentage withholding once to 0.01 with ROUND_HALF_UP before
subtracting. It is not yet an invoice-versus-payout rounding implementation.
Spain preview EUR 121 -> EUR 121 deposit, EUR 0 withheld, EUR 21 included tax.
The management result basis remains gross/tax-inclusive. No separate fee is
subtracted per deposit and no approximate EUR 36 expense is created.

Timing returns elapsed-hour guidance and weekend flag, not a computed due date
or holiday-aware cutoff. Missing Spain timing stays unknown. Cash/transfer fees
are not assumed zero. Reimbursement expectations/dates are configuration metadata,
not evidence of actual bank refunds. Policies currently apply per company/channel;
account/provider overrides are not implemented. Source-tax precedence, record
snapshots, actual-fee adjustments, bank matching and monthly calculations belong
to later processing phases. No real reports were imported.

## What you should test

Open http://127.0.0.1:3037/finance/configuration using the existing isolated
finance-review@example.test account and select Fees, timing & tax.

1. QA financial company (DOP): review Cierre/recurring 3.5%, Link 5%, 24–48-hour
   timing with possible weekend delays, and no sales tax. Test 100 for Cierre
   (96.50 deposit), then Link (95.00). Unconfigured transfer remains unknown.
2. QA spain company (EUR): card deposits are full; the independent fee and exact
   offer dates remain unknown, with approximate EUR 36/2027 preserved in notes.
   Test 121 -> 121 deposit and 21 included tax; result basis stays tax-inclusive.
3. Edit a timing setting and restore it. Add an overlapping active setting and
   confirm rejection. For a future rate, end the old rule the preceding day,
   then add the new dated rule and compare preview dates. Restore QA changes
   if you want to keep the confirmed defaults ready for the next phase.
4. Repeat Set up confirmed defaults: it must not duplicate or overwrite settings.
   Review English/Spanish labels if desired.

The DO and ES setup actions were already run in the isolated QA database.
QA second company remains available for an independent fresh setup test.
Normal production credentials are not used by this temporary database.

## Validation and environment

- 184 PostgreSQL 16 tests passed: 103 finance/access/configuration and 81 existing
  analytics/purchase/import regression tests. New policy coverage has 14 tests.
- Initial 12 policy tests also passed on isolated SQLite. Final Django check and
  makemigrations --check --dry-run passed. Frontend lint/build passed with existing
  unrelated lint warnings; no new finance lint warnings.
- Broad discovery of core_data also encountered its pre-existing core_data.tests
  import of removed Center. That legacy file was not changed. The supported
  regression modules listed above passed; this is not a claim that all legacy
  test modules are healthy.
- Browser QA: DO/ES initialization, fee/tax previews, overlap rejection, timing
  edit/restoration, persistence after reload and final layout verified.
- Local proof: /private/tmp/finance-phase2-4-preview.png. Test/build logs use
  /private/tmp/finance-phase2-4-{focused,pg-tests,lint,build}.log.
- Only temporary QA/test databases migrated. No normal local database, real user
  grants or production records changed. No source reports or credentials added
  to Git. Unrelated exports/ untouched. No external review agent used.

Apply migration 0005 before serving the updated backend, even when finance is
hidden. Compatible backend/frontend release order and earlier additive migrations
still apply. Local preview runs on frontend 3037/backend 8027 with QA settings.
No finance changes pushed, merged or deployed. Next gate is Phase 2.4 acceptance;
then Phase 3 import discovery under the agreed workflow.
