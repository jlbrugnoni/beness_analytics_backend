# Finance delivery progress

Updated: 2026-10-24.

## Current checkpoint

- Phase 1 foundation/access accepted on 2026-10-24; Phase 2.1 accepted (D-031); Phase 2.2 accepted (D-036); Phase 2.3 mapping discovery in progress (Q-009).
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
- Phase 1 acceptance: client confirmed "great, it works properly" (D-027). Phase 2 discovery answered (Q-007/D-028–030); Phase 2.1 accepted. Phase 2.2 accepted. Phase 2.3 Q-009 sent; 2.3–2.4 and 3–7 code not implemented.

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

Phase 2.2 accepted. Answer Q-009 in QUESTIONNAIRE.md or PHASE_2_3_DISCOVERY.md.
No new application changes accompany this discovery checkpoint.

## Next work

Resolve Q-009 source-reliability questions, then implement Phase 2.3 mappings.
Spain method names may remain unconfigured if not yet available. Later steps add source mappings and historical-baseline/
dated fee/tax rules. Imported movements, expected balances and sensitive payment
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
