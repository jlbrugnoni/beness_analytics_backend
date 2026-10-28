# Finance delivery progress

Updated: 2026-10-25.

## Current checkpoint

- Format correction D-069: normal Alegra payment uploads support original XLSX directly. See PAYMENT_XLSX_CORRECTION.md; client retest pending.

- Latest: Phase 3.3.3.1 payment preview accepted (D-066); Phase 3.3.3.2 shared receipt/routine import processing implemented and validated, client acceptance pending. Historical financial migration is not complete. See PHASE_3_3_3_2_DELIVERY.md.

- Phase 1 foundation/access accepted on 2026-10-24; Phase 2.1 accepted (D-031); Phase 2.2 accepted (D-036); Phase 2.3 accepted (D-039); Phase 2.4 accepted (D-042); Phase 3.1 accepted (D-048); Phase 3.2 accepted (D-051); Phase 3.3.1 Alegra previews accepted (D-056); Phase 3.3.2 sales posting/review/undo accepted (D-059); Phase 3.4.1 migration source previews implemented; client acceptance pending.
- Phase 0: accepted on 2026-10-24 with "perfect, we can continue" (D-026).
- Subphase 0.2: main business discovery batch resolved; all 12 consolidated
  answers and three focused clarifications recorded. DR-first editable account
  setup is sufficient; no complete inventory is required before foundation work.
- Q-005 administration formula accepted: gross sales before processing fees,
  expense-month weights, pending/manual split when no income. Detailed allocation
  edge cases remain phase-specific. Signed extraordinary result and tax-category
  boundary are confirmed; exact category mapping belongs to setup.
- Q-006: configurable sales tax accepted with client-provided defaults of
  inclusive 21% IVA for Spain and no sales tax for Dominican activity. V1 uses
  tax-inclusive sales/expense totals and allocation income; net-of-tax results
  and expense-tax capture are deferred. Spain uses Mindbody Sales in v1, with
  detailed adapter validation in Phase 5; future Alegra cutover is deferred.
- Subphase 0.3: field dictionary and textual screen/workflow drafts prepared.
- Subphase 0.4: 30 acceptance scenarios and reference calculations prepared;
  financial-processing scenarios remain planned, separate from Phase 1 tests.
- Phase 1.1: finance app, feature flag, routes and migrations implemented.
- Phase 1.2: company/account foundations and integrity/scope checks implemented;
  no real initial data seeded; configuration UI belongs to Phase 2.
- Phase 1.3: nine group/user finance flags, effective-source explanation, audit,
  stale checks and atomic user/profile saves implemented. Sensitive detail grant
  exists; transaction/category redaction awaits their later models.
- Phase 1.4: group editor, user form switches and protected finance landing
  implemented in English/Spanish. Validation described in PHASE_1_DELIVERY.md.
- Phase 1 acceptance: client confirmed "great, it works properly" (D-027). Phase 2 discovery answered (Q-007/D-028–030); Phase 2.1 accepted. Phase 2.2 accepted. Phase 2.3 Q-009 answered, implemented and accepted; Phase 2.4 accepted. Phase 3.1 bank preview/history implemented; bank posting/review/undo now implemented; sales imports, historical migration and Phases 4–7 not implemented.

## Branches and working tree

Current backend/frontend branch: `feature/finance-phase-2`.
Phase 0 branch was `feature/finance-phase-0`. See Git log for local checkpoints.
Implementation checkpoints: backend `4c0bf21`, frontend `630739e`. Subsequent
documentation-only checkpoint records this handoff; implementation hashes remain
the references for the tested code.
No finance changes pushed, merged, or deployed.
Backend already had an unrelated untracked `exports/` directory; leave it intact.
The frontend working tree was clean before the documentation pointer was added.

## Completed work

- Inspected the existing Django apps, studio/user models, access resolution,
  permissions, imported sales model, frontend access hooks, and route protection.
- Created the finance documentation index, working agreement, business rules,
  proposed architecture, roadmap, decision log, discovery register, and this log.
- Included enriched historical migration as first-version scope and an explicit
  overlapping-raw-upload acceptance scenario.
- Recorded the confirmed Estepona terminal and DDMM extraction rule.
- Added a frontend pointer to the canonical backend specification.
- Recorded Bewellness Group SL as Spain's Caixa owner and the Dominican
  operating/savings workflow. Added an internal-movement design with unmatched
  counterpart handling, preserving source movements.
- Documented gross-to-net AZUL reconciliation and separately charged fees.
  Unidentified separate AZUL charges still need classification.
- Recorded accepted policies P-001/P-002, decisions D-007–D-011, and acceptance
  A-19 with an illustrative result and actual-fee adjustment example.
- Sent Q-004 covering initial finance roles, role assignment, studio editing,
  and payroll visibility; later consolidated answers resolved the v1 approach.
- Recorded the client's preference for current groups/user flags/site limits.
  Selected group capability defaults plus additive user grants, documented the
  existing backend group support and missing frontend editor, and updated the
  roadmap/acceptance cases. Separate per-studio role assignments are deferred.
- Sent Q-005's shared-expense allocation question. No permission code has changed.
- Recorded the weighted administration workflow and both follow-up answers in
  BR-032/D-013/D-014. Added allocation structure and acceptance A-21/A-22 for
  expense-month weights, no-income fallback, rounding, and access-independent
  calculation. This is specification work; no allocation engine exists yet.
- Sent Q-006's tax-presentation question for the monthly result. Initial account
  and source/access definitions were subsequently resolved for the v1 scope.
- Recorded D-015/BR-033 and tax-profile design. Added inclusive-tax acceptance
  A-23 and preserved the distinction between bank collection, sales base, and
  expense tax. No tax calculations or settings exist in runtime code yet.
- Recorded D-016/BR-034 selecting tax-inclusive results and updated A-23. Removed
  the proposed net-of-IVA result from v1 acceptance; expense-tax/net reporting is
  a future enhancement rather than a blocker for this version.
- At the client's request, consolidated remaining business questions into
  QUESTIONNAIRE.md with 12 numbered items and links to discovery/phase dependencies.
  Answers to that batch are now recorded; settled definitions are not reopened.
- Recorded all 12 answers and follow-up confirmations: provenance/manual entry,
  coverage, editable taxonomy, Caixa reimbursements, refunds, signed final result,
  operating employment taxes, sensitive categories, deferred closing, and chosen
  rounding-review default. See D-017–D-025/BR-035–040.
- Added FIELD_DICTIONARY.md and WORKFLOWS.md; reconciled architecture/roadmap with
  the latest source and scope decisions. These documents describe future behavior.

## Phase 1 validation

- PostgreSQL 16 isolated database: 120 tests passed (39 finance/access plus 81
  existing analytics/purchase/import regressions).
- SQLite isolated focused tests: 38 passed before final API-root addition.
- Django system/migration consistency checks passed; frontend lint/production
  build passed with existing warnings.
- Browser QA with synthetic local data verified group save, immediate revocation,
  finance redirect, restoration, and finance/company layout.
- Documentation links/references and whitespace verified. Planned transaction
  acceptance scenarios are not claimed as complete.
- Only isolated temporary QA/test databases were migrated. Existing local app DB
  and production data were not changed. No real grants were assigned.

## What the client should review

Phase 3.4.1 workbook previews ready for testing; see PHASE_3_4_1_DELIVERY.md.
Q-015 answered (D-060–063). September 2026 chosen; current full saved source
copy and September 14–30 bank-report paths remain requested.
Dedicated Posting QA account contains synthetic posting/correction/undo examples;
pre-existing user-uploaded QA previews are retained.

## Next work

Client preview acceptance, then Phase 3.4.2 assignment/provenance and migration
decisions. Obtain current saved full source and second bank report before claiming
a complete September comparison. Other business definitions remain settled.
Q-012 answered (D-049–050).
Q-011 answered (D-043–046); September 2026 pilot selected by Q-015 (D-060).
Exact Spain method aliases remain editable and unconfigured until supplied.
Exact Caixa fee amount/frequency and offer dates remain optional setup follow-up. Calculated balances and category-aware sensitive payment
redaction remain future processing work.

## Delivery history

| Date | Delivery | Verification | Client acceptance |
| --- | --- | --- | --- |
| 2026-10-24 | Phase 0 baseline documentation and first discovery batch | Documentation checks only | Pending |
| 2026-10-24 | First discovery answers, company ownership, internal movement and fee definitions; follow-up batch sent | Documentation checks only | Exact P-001/P-002 policies pending |
| 2026-10-24 | Internal-movement presentation and monthly fee basis confirmed; Q-004 role discovery sent | Documentation checks only | P-001/P-002 accepted; Phase 0 remains open |
| 2026-10-24 | Client selected current-style groups/user/site permissions; group editor and additive user grants documented; shared-expense discovery sent | Documentation checks only | D-012 recorded; Phase 0 remains open |
| 2026-10-24 | Administration allocation and both formula follow-ups accepted; architecture and worked acceptance cases updated | Documentation checks only | D-013/D-014 accepted; Phase 0 remains open |
| 2026-10-24 | Configurable tax defaults recorded; monthly IVA presentation follow-up sent | Documentation checks only | D-015 accepted; result/expense definitions remain open |
| 2026-10-24 | Tax-inclusive v1 result selected; expense-tax/net comparison deferred | Documentation checks only | D-016 accepted; Phase 0 remains open |
| 2026-10-24 | Consolidated remaining discovery into 12 numbered questions at client request | Documentation checks only | Answers pending |
| 2026-10-24 | All consolidated answers and clarifications recorded; field dictionary, workflows and 30 acceptance cases prepared | Documentation/reference checks only | Phase 0 draft ready for client review |
| 2026-10-24 | Client accepted Phase 0 and authorized continuation | D-026 recorded | Phase 0 accepted |
| 2026-10-24 | Phase 1 foundation, group/user permissions, protected finance APIs/UI and atomic audited access saves | 120 PostgreSQL tests; lint/build; Django checks; synthetic browser QA | Client acceptance pending |

| 2026-10-24 | Client confirmed "great, it works properly" after the Phase 1 test checklist; Phase 2 discovery prepared | Client feedback; documentation update only | Phase 1 accepted (D-027) |

| 2026-10-24 | Client supplied DR accounts/8 terminals/3.5% and 5% fees, zero savings baseline; Phase 2.1 accounts/terminal UI/API implemented | 133 PostgreSQL tests; lint/build; Django checks; synthetic browser QA | Phase 2.1 client review pending |

## Phase 2.1 validation

See PHASE_2_1_DELIVERY.md. 133 PostgreSQL tests passed (52 finance/access/config
and 81 existing regressions). Frontend lint/build and Django checks passed.
Only temporary QA/test databases changed. Expected balances and fee rules are
not implemented. No raw reports imported and no production deployment performed.

Phase 2.1 implementation checkpoints: backend `4969ab0`, frontend `eed0e6e`.

## Phase 2.2 discovery checkpoint

2026-10-24: client accepted Phase 2.1 with "perfect, we can continue" (D-031).
Extracted the existing 10-category/44-pair catalog read-only and compared used
category pairs. Recorded the additional Otros / Extraordinarios and invalid 1 / 1.
Sent Q-008 as one numbered batch; no category code or proposed defaults applied.

## Phase 2.2 implementation checkpoint

2026-10-24: all Q-008 answers received (D-032–035). Implemented editable two-level
company catalogs, shared baseline codes, one-time initialization, inherited
privacy/active/defaults, scoped/audited/revision-aware writes and EN/ES category UI.
153 PostgreSQL tests passed, plus 20 focused category tests on SQLite. Frontend
lint/build and Django/migration checks passed. Browser QA and exact boundaries
are recorded in PHASE_2_2_DELIVERY.md. Client acceptance pending; no production
changes. Phases 2.3–2.4 and financial processing remain unimplemented.

Phase 2.2 implementation checkpoints: backend `3670958`, frontend `0b36d89`.

## Phase 2.3 discovery checkpoint

2026-10-24: client accepted Phase 2.2 (D-036). Inspected Alegra mapping labels
read-only and existing operational PaymentMethod/SaleLine links. Recorded
source-field evidence and sent Q-009 as a numbered batch. No new application
code, migrations, reports or configuration defaults applied. Existing local QA
preview remains unchanged; production remains untouched.

## Phase 2.3 implementation checkpoint

2026-10-24: Q-009 answered (D-037–038). Implemented editable source aliases,
DR missing-only setup with explicit studio picks, interpretation helper and
read-only test area, scope/audit/stale protections and EN/ES UI. Exact Mindbody
aliases remain unguessed. 170 PostgreSQL tests passed, 17 focused SQLite tests,
Django/migration checks and frontend lint/build passed. Browser QA verified
setup, source ambiguity/manual recurring correction and mapping edit restoration.
No reports imported, financial corrections persisted or production changes made.
Client acceptance pending. See PHASE_2_3_DELIVERY.md for exact boundaries.

Phase 2.3 implementation checkpoints: backend `0511e8a`, frontend `040f394`.

## Phase 2.4 discovery checkpoint

2026-10-24: client accepted Phase 2.3 with "it looks good" (D-039).
Prepared Q-010 as one numbered batch, covering Caixa gross/net deposits, fee/offer
terms and DR settlement timing. Confirmed DR rates and tax-inclusive result
policy are retained. Answers pending; unknown fees must not become zero.
Documentation only; no new runtime configuration, migrations or app behavior.

## Phase 2.4 implementation checkpoint

2026-10-24: Q-010 answered (D-040–041). Implemented dated FeePolicy,
SettlementPolicy and TaxProfile, missing-only country setup, scope/audit/stale
checks, EN/ES editors and read-only calculations. Confirmed DO rates, typical
weekend-delayed 24–48 hours and Spain full deposits/21% included tax are available.
Approximate Caixa fee and offer end year remain notes, not invented exact terms.
184 PostgreSQL tests and frontend lint/build passed; Django/migration checks clean.
Browser verified setup, estimates, overlap rejection and timing edit/restoration.
Client acceptance pending. PHASE_2_4_DELIVERY.md records boundaries and legacy
core_data.tests discovery failure. No financial processing or production changes.

Phase 2.4 implementation checkpoints: backend `17e687a`, frontend `fe337a8`.

## Phase 3 discovery checkpoint

2026-10-24: client accepted Phase 2.4 with "we can continue" (D-042).
Reviewed the import roadmap, provenance/manual-preservation rules and existing
core_data import entry points. Existing operational imports are not the finance
write path. Prepared Q-011 as one numbered batch: bank download coverage,
Alegra item completeness, migration pilot period and proposed audited undo.
Answers pending; no proposed undo policy is treated as accepted.
First delivery target is bank previews/totals/history for Popular and Caixa,
followed by financial commit/overlap handling, Alegra and enriched migration in
separate reviewable steps. No new code/migration, reports or database changes.

## Phase 3.1 implementation checkpoint

2026-10-24: Q-011 answered (D-043–046). Added immutable bank preview batches/raw
rows, versioned Popular/Caixa CSV readers, scoped history/row/original endpoints
and EN/ES upload/inspection UI. Original bytes retained privately in the database;
full account and sensitive-detail grants protect unclassified sources (D-047).
Identical previews link to earlier files without collapsing occurrences. No
financial transactions, overlap matches or undo operations are implemented yet.
198 PostgreSQL tests, 14 focused SQLite tests, Django/migration checks and
frontend lint/build passed. Read-only original-file totals and synthetic browser
checks recorded in PHASE_3_1_DELIVERY.md. Client acceptance pending. Normal local/
production data and grants unchanged; only synthetic QA setup and batches changed.

Phase 3.1 implementation checkpoints: backend `472d66c`, frontend `d0b3250`.

## Phase 3.2 discovery checkpoint

2026-10-24: client accepted Phase 3.1 with "perfect. it worked well" (D-048).
Reviewed accepted overlap/manual-preservation/undo boundaries and prepared
PHASE_3_2_DISCOVERY.md. Q-012 asks only remaining undo authority and treatment
of proposed bank amount/date corrections. Both recommendations remain proposals,
not accepted business policy. Independent new rows must remain importable and
raw history must be retained under already accepted rules.
Documentation only; no financial posting, code, migrations or data changes.

## Phase 3.2 implementation checkpoint

2026-10-24: Q-012 yes/yes recorded (D-049–050). Implemented financial bank
postings/movements, source occurrence links and decisions, ledger revision plans,
audited explicit correction review, undo previews/reversals and ownership rules.
Partial undo protects edited/reconciled/corrected or independently supported
movements. Source batches/rows retained. No sales/results/classification claims.
217 PostgreSQL tests pass, including two real concurrent-import cases. Focused
SQLite tests, frontend lint/build and Django/migration checks documented in
PHASE_3_2_DELIVERY.md. Browser verified synthetic commit/retry/review/history/undo.
Client acceptance pending. No real financial movements were created by the agent;
normal/production DB and real grants unchanged. Dedicated synthetic QA setup only.

Phase 3.2 implementation checkpoints: backend `8de1698`, frontend `7a343fd`.

## Phase 3.3 discovery checkpoint

2026-10-25: recorded Phase 3.2 client acceptance (D-051). Prepared
PHASE_3_3_DISCOVERY.md and Q-013 on numbering reuse, approval of changed invoice
snapshots, split payments, and cancellation/credit-note export behavior. Settled
source, payment-date, studio, tax and Spain decisions remain unchanged.
Documentation only; no new runtime changes or application tests. Real uploaded
QA files and financial postings were not changed. No push, merge or deployment.

## Phase 3.3.1 implementation checkpoint

2026-10-25: Q-013 answers recorded (D-052–055). Added immutable finance-owned
Alegra item/invoice source previews and private API/UI; no financial sales posted.
Validated original report read-only (438 invoices/456 items/DOP 2,574,587.60).
18 sales tests, PostgreSQL regression suite 235 passed; SQLite 233 passed/2 skips;
frontend lint/build and Django consistency checks passed. Browser synthetic upload,
repeated-item detail and review filter verified. Existing QA data retained.
Client acceptance pending. Exact cancellation label is still requested; unknown
statuses remain for review. See PHASE_3_3_1_DELIVERY.md for limits and test steps.

Phase 3.3.1 implementation checkpoints: backend `2fff6e9`, frontend `bb988ee`.

## Phase 3.3.2 discovery checkpoint

2026-10-25: client accepted Phase 3.3.1 with "it worked well" (D-056).
Prepared PHASE_3_3_2_DISCOVERY.md and Q-014: carry forward exact cancellation
status, clarify whether cancelled/reissued invoices sometimes keep the payment
without refund. Existing original-period/no-double-deduction policy is unchanged.
Documented invoice identity, immutable fact anomalies, source overlap, assignment
preservation, stale checks and audited undo using already accepted authority.
Documentation only: no runtime/data changes or new application tests. Existing
QA data retained. Both repositories remain feature/finance-phase-2; no deployment.

## Phase 3.3.2 implementation checkpoint

2026-10-25: Q-014 answered (Anulada; cancellation/reissue may keep payment),
D-057–058/BR-062–063. Added sales ledger, separate postings, explicit cancellation
review, mapping snapshots/manual assignment preservation, replacement/no-refund
classification, before/after audit and protected undo. No bank refunds or monthly
results fabricated. Existing QA user files/bank records unchanged; only dedicated
synthetic Sales posting QA company used for browser postings.
PostgreSQL 253 tests passed including 2 new races; frontend lint/build and Django
checks passed. See PHASE_3_3_2_DELIVERY.md for limitations and client checklist.
Client acceptance pending. No finance push, merge or deployment.

Phase 3.3.2 implementation checkpoints: backend `13448a9`, frontend `d08de4a`.

## Phase 3.4 discovery checkpoint

2026-10-25: client accepted sales posting/review/undo with "you can cotinue"
(D-059). Prepared PHASE_3_4_DISCOVERY.md and Q-015 covering completed Dominican
pilot month, current source workbook, cash-entry provenance and split payment
representation. Settled legacy review-flag and manual-preservation rules retained.
Documented preview, assignment/provenance foundation and pilot comparison sequence;
no migration models/code implemented or private source re-read at this checkpoint.
Documentation checks only; existing QA/normal/production data unchanged. Both
repositories remain feature/finance-phase-2; no push, merge or deployment.

## Phase 3.4.1 implementation checkpoint

2026-10-25: Q-015 answered D-060–063. Added native DR enriched XLSX previews,
immutable source/formula evidence, month-basis summaries/filters and protected
history/raw/original API/UI. No financial migration or account guessing. The
saved original path remains a partial Aug 31–Sep 2 sample (41 financial entries
plus an incomplete category row); full master and Sep 14–30 source paths requested.
PostgreSQL 269 tests passed; SQLite 265 passed/4 skipped; focused migration tests,
frontend lint/build and Django checks passed. Synthetic-only browser QA verified
cross-month values, cache errors and invalid-row retention. Client acceptance
pending. No changes to existing bank/sales postings or grants; no deployment.

Phase 3.4.1 implementation checkpoints: backend `7a025d4`, frontend `01df158`.


## Phase 3.4.1 source display correction

2026-10-25: corrected Excel storage indexes/date serials in Source cells with
readable original column names, decoded text, dates, periods, amounts and Yes/No.
Existing uploaded evidence stays immutable; no re-upload required. Full workbook
BI2 and both September Popular reports found in app; observed workbook dates
Sep 1–Oct 22, September 313 movements. Alegra item/admin invoice counts differ
(611/615), and source-bank/workbook comparisons remain pending; source presence
does not certify reconciliation. See PHASE_3_4_1_DELIVERY.md for aggregate evidence.
190 finance tests discovered: 186 passed / four existing PG-only skips on SQLite;
frontend lint/build and synthetic browser QA passed. No financial changes or
push/merge/deployment. Client acceptance pending; next is existing-upload retest.


## September invoice comparison and source selection

2026-10-25: D-064 confirms original item-level Alegra as sales source of truth.
Read-only comparison explains 611 invoices versus 615 administration payment
entries: four split-payment pairs, plus one uncoded administration row against
one unmatched Alegra code. Date/amount/studio match on the candidate, but customer
names differ; no confirmed link. Two common invoices have amount differences,
one also payment/invoice-date and outstanding-status evidence. No workbook or
financial changes. See SEPTEMBER_ALEGRA_COMPARISON.md for exact codes and rows.
This corrects the earlier “615 invoice numbers” wording. Historical mixed methods
need review before reconciliation; current no-split assumption is not silently
changed. Source-display acceptance and financial pilot validation remain pending.


## Dual Alegra report workflow planning

2026-10-25: D-065 records client confirmation of complementary invoice and payment
reports, including historical mixed payments. Reviewed existing invoice posting:
one FinancialSale with a single source channel; no receipt/allocation importer.
Documented recommended invoice → payment → bank sequence with safe pending links
for other arrival orders, identity/retry rules, conflict review, dependent undo,
privacy and incomplete-evidence handling. Inserted Phase 3.3.3 dependency before
historical posting. Native unmodified payment export is needed to define identity
and layout safely; no report-menu name or stable ID is assumed. Source version
explanation recorded without mutating September evidence. Documentation checks
only; no implementation, workbook/financial mutation or deployment.


## Preview #3 payment-structure inspection

2026-10-25: found user upload #3; byte-identical duplicate of #2, not new source
versions. No reupload needed. Alegra_adm has 1,128 dated payments, 1,127 distinct
populated Numero values and one missing number. Every dated row carries exactly
one invoice code in original Asociaciones, including row 183 → B0200004842;
prior candidate-only conclusion based on derived NCF is superseded. No payment
link posted; missing receipt ID/customer-label discrepancy remain review evidence.
Recorded raw-versus-enriched method fields and source limitations in the dual
report import plan. Enough structure for workbook-preset preview design; standalone
native payment CSV support still unverified. Read-only analysis/documentation only.


## Phase 3.3.3.1 payment workbook preview delivery

2026-10-25: client said “perfect, continue” after source structure inspection.
Implemented derived read-only Alegra_adm previews on existing saved migration
workbooks: original invoice references, separate payment occurrences, preserved
manual methods/studio/review flags, invoice/review/month filters, grouping, totals,
pagination and readable source cells. Existing uploads need no source rewrite or
re-upload; payment posting/linking is not implemented. No financial/grant changes.
Real #3 read-only validation: 1,128 payments; September 615 /3,555,130.80 DOP;
one missing-number review entry with explicit invoice reference. These are source
checks only; invoice-vs-payment discrepancies and settlements remain unvalidated.
281 supported PostgreSQL tests passed; SQLite 277 passed/four skips; ten final
focused PG payment tests passed. Frontend lint/build, migration checks and
synthetic browser QA passed. See PHASE_3_3_3_1_DELIVERY.md for limits, evidence and
client checklist. No deployment/push/merge. Acceptance pending for this preview
and prior source display; next is receipt identity discovery and reviewed posting.


## Phase 3.3.3.2 shared payment/routine upload discovery

2026-10-25: client accepted payment preview (D-066), clarifying historical migration
is occasional setup, normally once; ordinary reports maintain the same history
thereafter (D-067). Recorded separate entry points feeding common financial records,
source identities, manual assignments and overlap/review/undo services. No recurring
enriched workbook requirement or separate migration ledger. Prepared
PHASE_3_3_3_2_DISCOVERY.md with concrete acceptance cases for migration→native and
native→migration overlap, pending links and manual preservation. Q-016 asks whether
payment Numero is permanent/company-wide unique and whether one receipt can cover
several invoices. Answers pending; no posting identity/cardinality assumption
implemented. Documentation checks only; runtime/data/grants unchanged. No push,
merge or deployment. Next: answer Q-016 and implement the shared payment structure.


## Phase 3.3.3.2 shared receipts / routine import delivery

2026-10-25: Q-016 answered (D-068). Implemented shared receipts and source/posting/
decision/event history, guarded company/provider/payment-number identity, one
invoice per receipt, several receipts per invoice, exact pending invoice links
in either arrival order and protected undo. Routine Payment imports screen and
strict observed-column CSV preset share the same services with existing-workbook
preparation; initial migration is now secondary setup navigation. Source conflicts
stay pending, independent valid rows proceed and manual channel corrections survive.
Migration 0011 applied only in isolated QA/tests. No real source posted, no grants
changed, no push/merge/deployment. Synthetic browser company #6/import #1 has two
linked receipts with one manual Recurring correction; repeated source plan #2
recognizes them. Real source #3 and its company financial receipts remain untouched.
PostgreSQL 299 supported tests passed; final focused PG18 and SQLite26/2 skips;
frontend lint/build and system/migration checks passed. See
PHASE_3_3_3_2_DELIVERY.md for exact scope, native-format limitation and client tests.
Client acceptance pending. Next: client receipt-processing test, then historical
assignment/provenance decisions and actual native payment export acceptance.

Phase 3.3.3.2 implementation checkpoints: backend `851418d`, frontend `7cfbebb`;
both on `feature/finance-phase-2`. These are local commits only.


## Routine payment XLSX correction

2026-10-25: D-069 corrects developer CSV-only assumption: Alegra_adm arrives as XLSX.
Routine Payment imports now accepts original XLSX directly, detecting one payment
table by observed columns across worksheet names/title rows. No enriched workbook,
Debitos/Ingresos sheets, CSV conversion or manual columns required. Shared receipt
identity/overlap/manual preservation remains intact; no financial source rewrites.
PostgreSQL 305 tests passed; SQLite299/6 skips; six new direct XLSX tests; frontend
lint/build and browser chooser/guidance check passed. Actual #3 read-only reader
check retains 1,128 payments without file errors. No real posting, schema/grant
change, push/merge/deployment. Client retest pending. See PAYMENT_XLSX_CORRECTION.md.

XLSX correction checkpoints: backend `382ce7f`, frontend `f05977e`; both on
`feature/finance-phase-2`, local commits only.


## Native transaction export #4: header detection and visible feedback

2026-10-25: Client's routine payment XLSX #4 was saved but unreadable because native
header labels differ from the prepared workbook. Verified the original read-only;
added explicit native aliases in routine parser v2. Actual source now yields 615
incoming payments totaling 3,555,130.80 DOP plus 67 unsupported outgoing rows retained
outside payment posting. Added prominent preview status, failed-history labels and
permission-guarded re-read of retained failed routine reports into a new immutable
preview. No real posting or source/grant/schema changes. PostgreSQL307 passed;
SQLite301 passed/6 skips; frontend lint/build and synthetic browser re-read passed.
Synthetic QA failed preview #5 / new preview #6 are unposted. Local servers restored
on 3037 / 8027. See PAYMENT_XLSX_CORRECTION.md for source observations, scope and
client test. Real #4 remains unchanged, ready for client re-read; acceptance pending.

Native-header correction checkpoints: backend `72ee773`, frontend `1de092f`,
both local on `feature/finance-phase-2`.


2026-10-25: D-070 records client clarification that native `Tipo de nota débito`
is transaction type: Ingreso = sales/collections, Egreso = organizational purchases.
Confirmed current reader excludes Egreso from incoming totals and posting guard
blocks it from creating receipts. Retained source evidence remains available.
Recorded future purchase-to-bank-debit matching and expense deduplication discovery
in ROADMAP; no new posting, matching, UI or data changes. Documentation-only update;
validated against reader/posting paths and existing native-kind regression test.


## Client daily workflow correction: D-071

2026-10-25: Client finds import-centered navigation and visible synthetic companies
confusing; requests one simple company/report upload page and separate Excel-like
all-record tables with filters, status indicators and edit dialogs. Reviewed current
Finance/Analytics screens and bank/sale/receipt API boundaries. Confirmed absence
of a complete operational bank-classification editor and cross-import workspace;
this requires bringing forward Phase 3.4.2/4 foundation, not cosmetic relabelling.
Added DAILY_WORKSPACE_PLAN.md with proposed UX-1–4 sequence, field editability,
manual-create/void permission recommendations and fixture-isolation safeguards.
Q-017 daily file inventory asked, pending. No UI, database, grant or real-record
changes. Documentation checked; no application tests warranted. Next: record file
inventory and implement workspace in bounded deliveries before September migration
certification, reusing existing import/identity/audit protections.


Q-017 answer: Dominican routine inventory is three uploads, combined bank debit/
credit + Alegra transactions + Alegra invoices/items. Updated workspace/roadmap;
four operational table tabs do not imply four files. Existing Spain source policy
remains unchanged. Next delivery can proceed with the Dominican selector contract.


2026-10-25: D-072 further simplifies the proposed workspace to three primary tabs
(Bank debits, Bank credits, Invoices). Both Alegra sources enrich one invoice table;
invoice dialog exposes items and individual linked payment method/studio corrections.
Q-018 explicitly confirms amounts/numbers/client facts are read-only; later reports
and source-change review supply changes. Updated DAILY_WORKSPACE_PLAN.md, decisions,
discovery and workflows; proposed studio inheritance/manual override and unlinked-
payment review safeguards are documented, not delivered. Documentation-only; no
application tests, source/data/grant changes, push or deployment. Implementation
of the simplified workspace remains next.


## Daily workspace UI delivery (D-071/D-072)

2026-10-25 client timezone: implemented Records as finance landing with three tabs,
company/filter/sort/pagination/full-query amounts and original evidence. Added one
Upload page for the three Dominican report types, source range/count/preview,
existing service confirmation and secondary history. Invoice dialogs show items
and individual payment method/studio edits; audited studio override/inheritance is
the only added assignment capability. Read-only source facts protected; old import
review/undo URLs remain usable via exact batch links. No company cards, schema/data
migration, real posting, source rewrite or grants changed. Test-company entities
remain in isolated QA without deleting/moving real uploaded reports.

PostgreSQL313 passed; final focusedPG50 passed; SQLite307/6 skips; frontend lint/
build and Django/migration checks passed. Browser synthetic invoice300/two payments,
studio-inheritance save preserving Recurring, source evidence, saved-source native
confirmation and unlinked-payment access verified. Synthetic company6 now has four
receipts after committing synthetic preview6 (101/102 unlinked + prior990001/990002).
Real report4 unchanged/unposted. See DAILY_WORKSPACE_DELIVERY.md for exact scope,
limits and client tests. Acceptance pending. Bank classification/manual cash/create-
void services, full pending queue/fixture isolation and historical certification
remain next bounded deliveries; reconciliation/results/release are not delivered.

Daily workspace checkpoints: backend `77cba6a`, frontend `356cdbc`, local on
`feature/finance-phase-2`. Local QA backend8027/frontend3037 restored after build.


## Bank debit/credit classification and simpler import label

2026-10-26: first workspace accepted by client (“perfect, it worked”). Client asked
for bank editing and clearer meaning of the advanced link, then authorized continue.
Implemented optional BankMovementClassification (migration0012) and audited scoped
bank edit/options/detail services. Records now edits description, categories, studio/
administration, method/terminal, movement kind, expense month or operation date and
recognition separately from reconciliation. Source facts/identity protected; existing
imports/review/undo reused and edited assignments survive overlap/source corrections.
Import details replaces the verbose label. PostgreSQL322 passed; SQLite316/6 skips;
lint/build/system/migration checks passed. Isolated QA0012 applied; synthetic company6
account5 /movements354credit,355debit tested with no real posting/source/grant changes.
Browser caught date/month-control persistence issue; replaced with validated explicit
text fields and verified saved date/month via read-back. See BANK_CLASSIFICATION_DELIVERY.md.
Client acceptance pending. Next remains manual/cash/provenance/migration and later
reconciliation/results; no production schema migration, release, push or merge.

Bank classification checkpoints: backend `11b81ab`, frontend `6566acd`; local
`feature/finance-phase-2`. QA frontend3037/backend8027 restored after final checks.

2026-10-26 follow-up: client found mandatory bank edit comments too burdensome.
Made routine bank classification comments optional while preserving audit/revisions,
permissions and source-correction/undo reason requirements. Added bilingual movement
kind examples. Focused tests28 passed/2 PostgreSQL-only skips; frontend lint/build
passed. See BANK_CLASSIFICATION_DELIVERY.md. Client acceptance pending.

2026-10-26: client corrected concept: categories/subcategories belong only to debit
expenses. Removed credit category UI/filter/options; reject credit assignments in API.
Added missing terminal recognition to new posting plus explicit audited catch-up for
existing credits, respecting account/studio scope, manual conflicts and review locks.
PostgreSQL44 passed; SQLite42/2 skips; lint/build passed. Synthetic browser verified
new automatic mapping and catch-up of1 older credit. No real financial records changed.
See BANK_CLASSIFICATION_DELIVERY.md. Client acceptance pending; branches remain local.

2026-10-26: client requested a compact bank dialog and a reliable processed flag.
Removed persistent source/missing-data alerts, moved source details to header info
icon, added live required-field markers. Reviewed now requires complete applicable
assignments in UI/API; partial work saves, removing required data clears review.
Legacy incomplete flags appear in Not reviewed queue. PostgreSQL46 passed; SQLite44/
2 skips; lint/build passed. Synthetic browser verified source icon, partial/complete
saves, automatic uncheck and queue exclusion. See BANK_CLASSIFICATION_DELIVERY.md.
Client acceptance pending; no production release or real-data changes.

2026-10-26: client simplified movement kinds to debit Expense/Internal/Refund and
credit Income/Internal/Refund-reimbursement/Extraordinary. Added unreviewed direction
defaults on posting, API/menu restrictions and legacy-compatible presentation/audit.
Migration0013 choices metadata applied only isolated QA/tests. PG50 passed; lint/build/
migration-drift checks passed; browser lists verified. Invoice studio comes from
invoice cost-center mappings; linked payments inherit it. Client asked about a reset:
recommended an isolated clean dataset, no reset performed. See BANK_CLASSIFICATION_DELIVERY.md.

2026-10-26: client accepted simplified types and requested grouped monetary displays
(e.g.2,680,750.98). Added one decimal-string display formatter throughout finance
records/dialogs/imports/source details/migration/config balances/fee previews, with
2 decimals and comma grouping independent of UI language. No API/storage/calculation/
identity changes; raw report evidence remains intact. Numeric setup inputs retain
raw values with formatted helper previews. Client agrees to keep developing/tests
before reset; ROADMAP.md now defines a clean-replay checkpoint after the first full
imports→classification→reconciliation→monthly-result workflow and before migration
certification/rollout. No reset performed. Validation details follow delivery checks.

Monetary display checks completed: 14 formatter checks, lint (existing unrelated
warnings) and production build passed; browser synthetic358 verified grouped amount/
balance/total/header/source fields. No backend behavior/schema changes. Details in
BANK_CLASSIFICATION_DELIVERY.md; reset checkpoint in ROADMAP.md. Local QA restored.

2026-10-26: client explicitly requested immediate reset for an August2026-only replay,
overriding D-078 timing. Completed all finance transactional/import data reset in
isolated local QA, after verified full DB/source-blob backup at .local-backups/
finance-reset-20261026T113558 (outside Git).358 bank movements/443 invoices/619 receipts
and all preview/history rows removed; all22 scoped tables empty.56 other/configuration
models verified unchanged by hashes, foreign keys valid,12 empty-workspace API checks
passed and browser confirmed. Companies/accounts/terminals/categories/mappings/policies/
users/permissions/non-finance data retained; sequences retained, ledger tokens advanced.
Backend8027 restored, frontend3037 running. No reset of production or analytics. Next:
client August workbook preview then routine report replay in same company. Historical
bank migration posting remains pending. See BANK_CLASSIFICATION_DELIVERY.md.

2026-10-26: client uploaded August–September1 workbook but could not import. Delivered
historical bank bridge and simpler all-date debit/credit screen with optional filters,
explicit bank-origin selection and existing posting/review/undo. Preserves source/manual
assignments, conservative overlap matching and cross-account/stale-plan safeguards;
explicit preview copy supports choosing the configured company without changing the
original. 271 finance PostgreSQL tests, frontend lint/build and migration-drift check
passed; synthetic browser two-row posting/classifications/reopen verified, fixture then
cleaned. Real preview6 remains unchanged/unposted (327 rows), bank ledger empty for
client replay. Migrations0014/15 applied only local QA/tests after verified full backup.
Local8027/3037 restored. Cash/manual ledger, reconciliation/results/certification remain
pending; client still selects correct company and confirms bank origin. See
HISTORICAL_BANK_POSTING_DELIVERY.md. No production release; client acceptance pending.

2026-10-26: client reports missing Alegra migration and confusing bank flags/fields.
Added named Alegra worksheet adapter, explicit all-date invoice/payment preparation
through existing posting services, workbook lineage migration0016 and numerical
representation normalization for XLSX/CSV invoice overlap. Historical screen now has
bank vs Alegra tabs; bank table prioritizes review, debit receipt fields hidden by
recommended default pending optional feedback. No review/reconciliation flags changed.
Client had posted322 bank rows; browser prepared only invoice9/payment9 from workbook8
(company1),744 invoices/746 payments, no real sales/receipt posting. Full source backup
preceded QA schema change.276 PostgreSQL finance tests, lint/build and drift checks
passed. Browser verified counts, invoice plan and expense-focused editor. See
HISTORICAL_ALEGRA_DELIVERY.md. No reset or production release; acceptance pending.

2026-10-26: client confirms "i think all is correct" after testing the historical
Alegra workflow and bank UI corrections. Mark this delivery accepted (D-082), including
the simpler debit fields and review-status presentation. No additional financial
posting, reset, production release or claim of fully certified history follows from
this message. Next acceptance exercise: routine September bank/Alegra reports in the
same company/account, checking overlapping September1 entries, duplicate prevention,
preserved manual assignments, split payments and pending source-change reviews.

2026-10-26: Mac restart removed the temporary working QA database/settings. Restored
the latest saved backup into a new persistent .local-finance working database, verified
integrity, applied0016 and restarted8027/3037. Login, finance API and frontend HTTP200
verified; same QA password verified/upgraded from legacy test hash without access
changes.322 bank movements and workbook previews restored; later Alegra test postings
were absent from that snapshot and must be repeated before September overlap tests.
Prepared Alegra previews only, no financial posting/reset. Added a persistent startup
launcher and LOCAL_TEST_RUNTIME.md; normal database/env and saved backup unchanged.

2026-10-27: read-only client September overlap audit completed against a consistent
private DB copy. Routine bank batch20 has175 rows:161 created,4 historical links,
10 pending. All14 September1 source occurrences remain represented by the14 existing
historical rows; no new overlap-day movement. Full period175 ledger occurrences and
credit/debit totals match report. All322 historical classifications and sources match
pre-import audit baselines exactly. Pending rows expose description-whitespace false
conflicts and weak reused-terminal candidates; equal6,800 credits need distinct balance
evidence. No decisions or data changed, no code fix/complete replay acceptance claimed.
No new routine Alegra reports are present yet; historical744 invoices/745 receipts only.
See SEPTEMBER_OVERLAP_AUDIT.md for evidence, limitations and recommended next changes.

2026-10-27: D-083 general money/cash foundation implemented locally. Records presents
Expenses/Income/Invoices; manual bank/cash creation, audited financial edits and
logical voids reuse account/studio/sensitive controls. General cash setup remains
explicit with unknown opening balance. Historical explicit Efectivo credits have
a separate idempotent cash preview/import, expenses default bank. Manual bank
statement overlaps require review. Fresh285 PostgreSQL tests and frontend lint/build
passed; schema0017 applied after verified backup, all legacy financial values intact.
Browser created only company1 cash account6 and inspected workbook8:4 new cash
receipts totaling26,860.00 DOP, unposted. Existing483 movements/744 invoices/745
payments and pending bank reviews unchanged. Client acceptance, closures, balances,
paired transfers, cash migration undo/corrections and monthly results remain pending.
See GENERAL_MONEY_LEDGER_DELIVERY.md. No reset, production release, push or merge.

2026-10-27: client reports document agreement and successful manual entries. D-083
general money/cash workflow accepted (D-084). Began daily closures discovery and
recorded staged comparison/allocation/exception plan in DAILY_CLOSURES_PLAN.md.
Two business confirmations remain: table presentation and multi-day deposit splitting.
Retain BR-040 rounding rule; initial redundant tolerance question withdrawn. Existing
models have no explicit financial reconciliation allocation ledger yet. No code/data
mutation, client entry cleanup, reset, release or independent certification performed.

2026-10-27: client clarifies monthly/all-days closure layout and declines deposit
splitting (D-085). Delivered read-only DR monthly per-method comparison and daily/
cumulative/evidence dialogs with optional studio scope, effective fee estimates,
review queues and explicit exclusions. Expected collections sum posted Alegra
payments once; invoice warnings remain visible without erasing valid payments.
No confirmation/reconciliation writes, deposit split, schema change, reset or
production release.293 PostgreSQL finance tests and frontend lint/build passed;
client acceptance pending. See MONTHLY_CLOSURES_DELIVERY.md. Spain Mindbody comparison,
explicit confirmations, verified balances and monthly results remain later work.
Browser follow-up: verified monthly/daily/source views and independent actual-source
filter. All33 finance table hashes unchanged across read-only verification, including
client manual entries;493 movements/744 invoices/745 payments remain. Shared flex
layout min-width corrected and route gate reuses existing financial-account access.

2026-10-27 D-086: client requests selectable month navigation and a quieter daily
table. Replaced native month input with localized month/year dropdowns and adjacent
month arrows. Removed running accumulated-difference column and duplicate total;
retained daily differences and one final monthly difference. UI-only, no backend
calculation/schema/data change. Validation and local commits recorded with delivery.

2026-10-27 D-087 operational release increment: V1 is DR operations only; Spain is
V2, with Financial Analytics after V2. Implemented comparison-only whitespace/strong
balance bank identity and ranked candidates; same-file replay in an isolated copy
linked173 existing rows, held2 debit identities and created0 movements, preserving
all493 sources/classifications. Actual batch20 still has10 saved pending decisions;
8 now have compatible unchanged candidates. No real import decisions were resolved.
Added audited company/day/method checks/reopen with existing reconcile permission,
nonzero-difference reasons, fresh-evidence/revision protection and dynamic Needs recheck
on changed support/fees. These are operational checks, not month locks, balancing
entries or mutations to individual reconciled flags. Added cash migration undo/restore
previews with source-ID retention, audit, ownership/scope/revision protection, checked/
edited/linked protections and restore overlap detection. Full304 PostgreSQL tests,
frontend lint/build, migration drift and whitespace checks passed.0018 applied to
local QA after private integrity-checked backup; all33 legacy finance table hashes
match after schema and browser verification. Browser verified exact-day optional
reason, nonzero-day disabled confirm without reason and cash recovery preview4eligible.
No real checks, cash recovery, source/assignment changes, reset, grants, push/merge or
production deployment. New check/event tables remain empty for client testing. Routine
September Alegra invoice/payment reports are still absent; September14–30 bank upload,
remaining identity reviews, client acceptance and real-cycle/production rehearsal
remain release gates. See DR_OPERATIONAL_RELEASE.md for scope, tests and cutover plan.

2026-10-27 closure history presentation: client confirms operational checks work.
Reopen history entries now show only action, actor and timestamp; the corresponding
check entry retains its comment. Stored audit events and financial data are unchanged.
Follow-up: display the returned history entries chronologically, with the first action
at the top and subsequent check/reopen actions below. API ordering and audit data remain
unchanged.

2026-10-27 operational access follow-up: added seven API regression tests for viewer
versus reconciler, each required visibility capability, live site/studio restrictions,
cross-company IDs, inherited group capability, inactive company/user and feature off.
Denied reads/writes preserve checks/events and hide review notes. All20 closure,
operational-check and new access tests passed in disposable PostgreSQL. No working
user/group permissions, financial records or schema changed. Documented the tested
matrix and real-partner acceptance in OPERATIONAL_ACCESS_VALIDATION.md. Real September
reports, remaining identity decisions, full-period comparison and cutover rehearsal
remain pending; asked client for available routine report upload names/numbers.

2026-10-27 second September bank overlap investigation: client uploaded bank21,
September14–30. Read-only audit confirms53 correct overlap links,32 new movements,
85 pending (50 credits/35 debits), all pending on16–30 with only different-day
candidates. Popular serial reuse causes all50 credit holds, including44 AZUL; generic
reference1 additionally causes26 debit holds. Existing v3 strong-match preference
does not prevent weak identifier-only candidates for genuinely new transactions.
Daily upload lacks direct review controls; older BankPostingPanel contains them.
Recorded source examples, counts and safe correction recommendation in
SEPTEMBER_SECOND_OVERLAP_AUDIT.md. No code/decision/data mutation in this investigation.

2026-10-27 D-088 delivery: implemented primary date/amount/description/balance matching,
Popular serial/generic reference guards, distinct balance handling, metadata/occurrence
review safeguards and v4 preview tokens. Added pending-only queue and audited atomic
apply-pending action using existing import/edit/account/sensitive gates. Daily upload
now exposes Review pending with ready-row confirmation and explicit side-by-side
link/create/source-correction decisions; no default candidate/action. Create/link use
standard audit notes; source correction/ignore retain required reasons.322 PostgreSQL
finance tests, changed-file frontend lint, production build and migration drift passed.
In a consistent disposable working-data copy, recovered85 report21 rows, preserving
all525 earlier movements/classifications,1214 invoices,1219 payments and6 checks/8
events. Repeat original CSV recognized170 rows and created0 new movements. Browser
verified preview and protected source-correction dialog without submitting real
decisions. Working report21 retains85 pending; report20 retains8 recognized/2 true
conflicts. Routine Alegra invoice/payment10 now available for full-period acceptance.
See BANK_MATCHING_V4_DELIVERY.md. No working financial writes/reset/grants/push/deploy.

2026-10-28 client reports D-088 recovery worked; audited real saved imports in a
consistent read-only snapshot. Report21 now has117 creations/53 links to170 unique
movements,0 pending;53 overlaps all reuse report20 records. Repeat report22 links the
same170 row-to-movement identities and creates0 movements. Reparsed originals/hash
and all four bank facts match; unique ledger income/expense totals equal the CSV.
No duplicate group includes report21 creations. Repeated-looking September expenses
have different balances. Broader historical scan found one old four-row payroll group
without enough identity metadata to distinguish from source alone; retained unchanged.
Recorded acceptance and limits in SEPTEMBER_BANK_DUPLICATE_ACCEPTANCE.md. Report20
still has10 pending decisions. This audit made no working financial or permission writes.

2026-10-28 record-editor close crash: reproduced expense Close causing TypeError
reading account_name from null. Parent clears the selected record before the MUI exit
transition/detail-reset effect finishes, leaving old detail content rendered briefly.
BankDialog now renders details/enables editing only when the selected record matches
the loaded movement; source/manual child dialogs use the same identity guard. Browser
verified imported expense/income Close returns to the table, nested manual expense/
income Close preserves the parent, and Escape dismisses the manual-expense parent.
No runtime error on these paths; changed-file lint passed. No financial writes or
backend/schema changes. The records screen remains open for client acceptance.
