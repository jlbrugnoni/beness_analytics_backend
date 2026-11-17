# Spain operational finance V2

Updated: 2026-11-16. Status: Steps 1–4 accepted for operational release; owner authorized deployment. Step 5 checks passed and backend/frontend production deployments succeeded.

## Delivery and acceptance agreement

Use `feature/finance-spain-v2` in both backend and frontend repositories. Each
numbered step is a separate delivery and, after explicit owner approval, a separate
commit in each repository that changed. Never commit, push, merge, deploy, or start
the next implementation step merely because automated checks pass. Present what
changed, validation evidence, limitations, and concrete owner tests. The owner may
request adjustments before accepting. Commit only on explicit instruction; moving
to the next step also requires the owner's direction. Keep uncommitted adjustments
within the current step until accepted.

No production data reset, local database publication, or original-report commits.
User-owned backend `exports/` remains excluded. Branch starting points are backend
`7b6b7a2` and frontend `6d9ac63`; retain existing unrelated room work.

## Confirmed scope

- Company: Bewellness Group SL; Spain, EUR; currently one studio, Estepona.
- Acceptance month: October 2026. Caixa sample covers September–October.
- Existing Analytics Mindbody Sales imports are the authoritative sales and
  collections source. Keep the current weekly add/update/unchanged workflow and
  require no second routine Mindbody upload to Finance.
- Financial source facts remain protected. Finance owns business assignments,
  review/reopen history, bank/cash receipts, expenses and operational day checks.
- Card deposits currently settle gross. Separate terminal fees and reimbursements
  stay as distinct movements. Unknown exact fee/offer dates remain configurable.
- Cash sales are expected collections, not proof of actual cash received. Actual
  cash receipts are recorded manually using cash accounts.
- Keep the current tax-inclusive operational comparison; net-tax financial
  analytics and management dashboards are a later module.

## Numbered delivery steps

| Step | Delivery | Owner acceptance |
| --- | --- | --- |
| 0 | Plan, branches and acceptance checkpoints | Review sequence and scope; no app behavior changed |
| 1 | Spain configuration and Caixa operation dates | Configure company/accounts/terminal/methods; import Caixa overlap without duplicates; inspect inferred dates and review exceptions |
| 2 | Mindbody-backed sales and payment records, including source refresh | Browse October sales/items/payments; repeat/change Analytics imports; verify protected facts, preserved overrides and audit/review behavior |
| 3 | Spain monthly closures and day checks | Compare Card/Cash by operation day; investigate differences; check/reopen days under existing permissions |
| 4 | Spain history and exceptional cases | Validate historical route if required, plus refunds, split payments, fees/reimbursements and transfers; verify incomplete coverage remains explicit |
| 5 | Release rehearsal and handover | Test authorized user profiles, representative end-to-end imports/corrections, DR regression and production configuration plan |

### Step 1 — Configuration and Caixa

Reuse existing company, account, cash, category, terminal, source mapping and policy
screens. No hardcoded production IDs or setup writes during application startup.
Use the common editable category catalog. Configure exact observed aliases:

- `Efectivo` -> Cash.
- `Tarjeta de crédito (Visa/MC-No Auth)` -> Card.
- `Beness Pilates Estepona` -> the existing Estepona studio.
- Caixa terminal `369092994` -> Estepona / Card / the selected Caixa account.

Extend Caixa interpretation to retain bank date and infer operation date from an
unambiguous supported `ON <terminal> DDMM` description. Determine year using bank
date, including January deposits of December sales. Define and test a conservative
validity window; invalid or ambiguous dates stay pending rather than guessing.
Do not overwrite manual assignments, reviewed records or original bank evidence.
Include provenance for inferred dates. Preserve fees/reimbursements and cash
deposits without treating them automatically as customer card sales.

Owner tests: configuration editing; October terminal sample; non-terminal rows;
repeat/overlap upload; manual-date preservation. Automated tests also cover year
boundaries, impossible dates, ambiguity and studio/account scopes.

### Step 2 — Mindbody integration and records

Read existing `core_data.SaleLine` and its import/raw-row provenance, scoped to the
configured company/site and authoritative source policy. Group sales using source
context plus sale number; preserve item detail and separate payment-method totals.
Never apply Alegra's B/E invoice-number rules to Mindbody sale numbers. Currency
comes from validated company/source context, not a new assumption for all sites.

Decide and document the adapter/projection approach after examining record editor,
audit and source-change contracts. No company-wide rebuild on each invoice edit.
Whether source-linked reads or stored projections are chosen, Finance sees existing
production imports and subsequent changes without a duplicate upload workflow.

Build source refresh behavior into this step: unchanged imports are idempotent;
new rows appear once; changed rows do not leave stale duplicate payments or sales.
Preserve finance overrides and review locks; material source corrections create
visible history/review and invalidate affected checked-day evidence as appropriate.
Do not interpret a row missing from a partial weekly upload as deletion/cancellation.
Handle missing mappings explicitly. Do not infer customer refunds solely from
absence. Tests must cover amount/date/method/studio changes and overlap identities.

Records should present Mindbody sales with their items and payment breakdown,
source information and existing permission/reopen conventions. Use sales terminology
where appropriate; a Mindbody sale number is not asserted to be a fiscal invoice.

Owner tests: October has 107 sales, 116 item rows, EUR 8,534.25 total;
Card EUR 6,692.60 and Cash EUR 1,841.65. Test a repeat upload and a controlled
source change locally, followed by reversal, without changing production data.

### Step 3 — Closures

Extend DR-only backend/UI guards deliberately, retaining DR behavior. Use mapped
Mindbody paid amounts as expected collections. Compare Card against Caixa amounts
by operation date and Cash against manually recorded cash receipts. Source sales,
bank receipts and cash deposits must not be counted twice. No inferred actual cash
receipt from a Mindbody sale. Preserve missing-account/method/date review queues,
details dialogs, monthly navigation, totals, checks/reopen permissions and history.

Owner tests: October comparison, drill-through, filters, manual cash receipt,
check/reopen and changed source evidence. Initial file comparison has six differing
operation days (8, 15, 19, 24, 26, 27 October), net EUR 39.49 more deposited than
reported Card sales. This is sample evidence, not an accepted correction or proof
of complete settlement coverage. End-of-month settlement may need November data.

### Step 4 — History and exceptions

Confirm whether Spain needs historical workbook migration before this step. If so,
inspect the actual workbook and implement a supervised preview/import route using
existing migration permission and provenance/review conventions. Do not assume the
Dominican workbook parser supports Spain. If historical migration is not needed
for release, record the owner's explicit deferral and keep routine imports usable.

Validate real or clearly identified synthetic split-method sales and refunds; the
October sample contains neither. Respect the existing rule separating original
sale/result period from actual refund cash-flow date, without double adjustments.
Test terminal-fee debit/reimbursement, bank/cash internal movements and missing
source periods. Expected cash cannot substitute for a historical cash ledger.

Owner tests: relevant exception workflows and, if required, month-by-month migration
comparison. Additional source examples are requested only when not already available.

### Step 5 — Release readiness

Run targeted tests per step, then a full finance regression and relevant Analytics
import regression, frontend checks/build, migration drift and realistic timing
checks at this checkpoint. Verify permissions and company/studio isolation with
representative profiles. Rehearse repeated imports, source corrections, preserved
manual overrides and closures end to end. Verify DR operations still behave as
accepted. Prepare Spain configuration/activation and rollback instructions without
copying QA financial data or secrets. Production publication remains separately
authorized after acceptance; push does not prove deployment success.

## Progress register

| Step | Implementation | Automated validation | Owner acceptance | Commit |
| --- | --- | --- | --- | --- |
| 0 | Plan documented; local branches created | Branch/status inspected | Accepted: owner said to start | Included in Spain V2 release |
| 1 | Spain mapping setup and Caixa operation dates | 427 PostgreSQL finance tests; frontend lint; browser setup dialog; real-file rehearsal | Accepted: owner said to continue | Included in Spain V2 release |
| 2 | Mindbody source-linked sales, assignments and history | 439 PostgreSQL finance tests + final12 targeted; frontend lint/build; real-source repeat rehearsal; browser | Accepted: owner said to continue | Included in Spain V2 release |
| 3 | Spain monthly/daily closures and source drill-through | 448 PostgreSQL finance tests; frontend lint/build; browser October comparison | Accepted: owner said to proceed | Included in Spain V2 release |
| 4 | Real split payment and historical importer implemented; migration audited | 462 PostgreSQL finance tests; source/ledger totals agree; see audit | Accepted for release; remaining classifications are operational review | b7b3152 backend / 79cc16b frontend |
| 5 | Release verification and deployment runbook | 462 PostgreSQL finance tests, 18 Analytics import checks, frontend lint/build, no migration drift | Owner authorized deployment on 2026-11-16 | b7b3152 backend / 79cc16b frontend |

This register is updated at delivery, acceptance and commit, keeping those events
separate. The current checkpoint is owner production setup and smoke testing. See SPAIN_V2_RELEASE.md for deployment, setup and recovery.


## Step 1 delivery and owner tests

Implemented 2026-11-15, uncommitted on both feature branches. No schema migration.
Existing company/account/category/policy screens and Caixa CSV format are reused.
Spain initial mapping setup creates the three confirmed Mindbody aliases with
settings permission, company-wide scope, revision checks and atomic audit. Existing
rules, including inactive or customized rules, are preserved. DO retains eleven
initial mappings; ES has three. The frontend offers the corresponding setup dialog.

Caixa date recognition accepts a full ON <configured terminal> DDMM description
and a valid operation date zero to seven calendar days before the bank date,
including December deposits in January. Unknown terminals, malformed/ambiguous
text, impossible, future or older dates remain pending. Longer legitimate delays
can be entered manually. Reviewed/reconciled/non-receipt records, conflicting
assignments, manual dates and bank source facts are preserved. Compatible existing
unreviewed Caixa rows with a terminal but no date can receive a date through the
existing terminal mapping action in Records' overflow menu. New create events and
existing classify events explain the date inference. Nothing is auto-reviewed or
reconciled merely because a terminal/date was recognized.

Evidence: 427 finance PostgreSQL tests passed without skips; targeted SQLite run
had 78 passes and two PostgreSQL-only skips. No migration drift, frontend changed
files pass ESLint. Spain setup button and dialog verified in local browser without
saving. Full frontend production build remains for release checkpoint. Real-file
preview/plan/commit rehearsal on disposable database copy: 94 new movements,
45 terminal dates inferred; repeated file had 94 unchanged and zero new movements.
All remained pending review. The working database was unchanged by that rehearsal.
No production data, local configuration or permissions changed for setup.

Local tests use existing QA spain company, QA Estepona and Caixa - Cuenta operativa
(EUR). These fixtures already have full-deposit/21%-included-tax policies and are
not production names/IDs to copy. Local app is running at http://127.0.0.1:3037.

Owner tests:

1. Configuration -> Source mappings -> QA spain company -> Set up Spain mappings.
   Select QA Estepona for Beness Pilates Estepona. Save and inspect the three
   editable mappings. Repeat setup: no duplicate mappings should appear.
2. Configuration -> Terminals: create 369092994 on the existing EUR Caixa bank
   account, studio QA Estepona, channel Card terminal/Cierre.
3. Routine Upload: select QA spain company and its Caixa account, upload the supplied
   CSV, inspect preview and import. Original files stay outside Git.
4. Records -> Income: ON 369092994 0610 has bank date 7 October; expect operation
   date 6 October, terminal, studio and Card assigned, still pending review.
   Non-terminal rows must not receive terminal-derived operation dates.
5. Manually change an unreviewed income's operation date and save. Upload the same
   bank file again: expect no new movements and the manual date/assignments preserved.
6. Inspect history for the inference note. Spain sales/closures come in later steps.

Stop for owner feedback and explicit commit/progression instructions.
