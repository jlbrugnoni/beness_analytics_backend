# Finance module handover

Updated2026-10-29. Release target: `main` in both repositories; development branch: `feature/finance-phase-2`.
**Current phase: DR operational V1 acceptance and release preparation.**

September uploads now audited: [Current release recommendation](DR_V1_RELEASE_READINESS_20261029.md).

Current Jan–Aug data is imported. Owner accepted the missing-number payment review;
there are now 4,995 active invoices and 5,000 active payments. The next pre-release
increment implements supervised migration completion, explicit review locks, separate
routine/migration upload permissions and privileged reopening of entries/closed days.
See [Review workflow](REVIEW_WORKFLOW.md), D-095. Historical expense bank/business description interpretation is corrected in
[Expense description mapping](EXPENSE_DESCRIPTION_MAPPING.md). Owner accepted representative-day testing and authorized committing, merging and
pushing both repositories. Production configuration/data initialization remains a separate cutover step. Original invoice/payment identity and source correction flows remain available.
Spain is V2; financial analytics follows Spain. Do not treat older phase plans or
pending-acceptance statements as the current delivery status. Current readiness and
remaining gates are in [DR operational release](DR_OPERATIONAL_RELEASE.md) and
[Acceptance status](DR_V1_ACCEPTANCE_STATUS.md); chronological evidence is in
[Progress](PROGRESS.md).

Implemented and client-tested workflows include editable configuration, historical
bank/Alegra/cash migration, routine bank and dual Alegra reports, overlapping imports,
manual bank/cash income and expenses, classification, monthly/daily collections
comparison, operational checks/reopen/history and direct correction from closure
review queues. Income editors on Records close after successful save; failures stay
open. September21 Cierre was verified against saved data as82,025.00 expected/actual
and Checked. This is representative acceptance, not a certified full month.

The two Alegra reports have distinct authority: invoices/items provide invoice facts
and studio evidence, while transactions provide payments (including split payments).
Both arrival orders and repeat uploads passed actual-source rehearsals. Native
September reports are posted;611 invoices and615 payments have equal gross totals.
Historic/native encoding overlaps have scoped, audited recovery, accepted by client.
Bank14–30 September and repeat upload were accepted without duplicate creations.
Older bank20 still has10 pending decisions that require explicit resolution.

Source amounts, bank dates/descriptions/references and imported invoice/customer
facts are protected; business assignments are edited separately. Normal assignment
edits do not require a comment for bank/cash records. Operational checks are evidence
reviews, not month locks or coverage certification. No deposit splitting, verified
running-balance promise or paired transfer workflow is included in V1.

Remaining work is full-period operational/source comparison, representative cash/
transfer/internal/refund scenarios, real-profile access acceptance and production
cutover/backup rehearsal. Do not copy QA companies/accounts/users or the whole local
SQLite database into production. Do not reset client records, broaden permissions or
merge/push/deploy without the relevant user authorization.

## Documentation index

For local startup after restarting the Mac, see [Persistent local test runtime](LOCAL_TEST_RUNTIME.md).
The working finance database now lives in the project .local-finance folder, not /private/tmp.

Latest verification:333 PostgreSQL finance regression tests, frontend lint/build and
migration drift passed2026-10-28. A later small income-dialog save change passed
changed-file lint and client testing. Current read-only acceptance audit and next
client tests are in [DR V1 acceptance status](DR_V1_ACCEPTANCE_STATUS.md). Historical
audit documents below describe evidence at their own dates, not current queue counts.

| Document | Purpose |
| --- | --- |
| [DR V1 acceptance status](DR_V1_ACCEPTANCE_STATUS.md) | Current saved results, unresolved queues and next real-cycle tests |
| [Cutover and recovery runbook](DR_V1_CUTOVER_RUNBOOK.md) | Staging/production sequence, local restore/access evidence and outstanding owner decisions |
| [DR operational release](DR_OPERATIONAL_RELEASE.md) | Agreed V1/V2 sequence and deployment gates |
| [Closure review workflow](CLOSURE_REVIEW_WORKFLOW.md) | Issue filters and direct supporting-record editors |
| [Alegra September acceptance](ALEGRA_SEPTEMBER_ACCEPTANCE.md) | Both report orders, overlap/repeat rehearsal and accepted recovery |
| [September bank duplicate acceptance](SEPTEMBER_BANK_DUPLICATE_ACCEPTANCE.md) | Accepted overlap recovery and real-source duplicate audit |
| [Operational access validation](OPERATIONAL_ACCESS_VALIDATION.md) | Automated permission matrix and remaining real-profile acceptance |
| [Business rules](BUSINESS_RULES.md) | Accepted behavior, source facts, and outstanding definitions |
| [Architecture](ARCHITECTURE.md) | Module boundaries, proposed records, integration, and access design |
| [Field dictionary](FIELD_DICTIONARY.md) | Ownership, source/assigned fields, provenance, and calculation definitions |
| [Screen workflows](WORKFLOWS.md) | Setup, upload/manual entry, review, reconciliation, and result flows |
| [Roadmap](ROADMAP.md) | Phases, subphases, dependencies, and acceptance scenarios |
| [Decisions](DECISIONS.md) | Client decisions and changes to earlier definitions |
| [Discovery](DISCOVERY.md) | Questions, answers, and the decisions they affect |
| [Consolidated questionnaire](QUESTIONNAIRE.md) | Current numbered list for the client to answer together |
| [Progress](PROGRESS.md) | Actual delivery status, validation, branches, and next work |
| [Initial configuration](INITIAL_CONFIGURATION.md) | Confirmed accounts, terminals, historical fee defaults and savings baseline |
| [Phase 3.4.1 delivery](PHASE_3_4_1_DELIVERY.md) | Enriched workbook preview, source discrepancy, validation and client steps |
| [Phase 3.4 discovery](PHASE_3_4_DISCOVERY.md) | Historical migration scope, sequencing and Q-015 pilot/provenance questions |
| [Phase 3.3.2 delivery](PHASE_3_3_2_DELIVERY.md) | Sales posting, overlap, cancellation/replacement decisions and undo |
| [Phase 3.3.2 discovery](PHASE_3_3_2_DISCOVERY.md) | Sales posting/overlap design and remaining cancellation questions |
| [Phase 3.3.1 delivery](PHASE_3_3_1_DELIVERY.md) | Alegra source preview, invoice/item validation and client test steps |
| [Phase 3.3 discovery](PHASE_3_3_DISCOVERY.md) | Alegra invoice/item scope and Q-013 correction, numbering and payment questions |
| [Phase 3.2 delivery](PHASE_3_2_DELIVERY.md) | Bank transaction commit, correction review, overlap decisions and audited undo |
| [Phase 3.2 discovery](PHASE_3_2_DISCOVERY.md) | Commit/review/undo design and remaining authority/correction decisions |
| [Phase 3.1 delivery](PHASE_3_1_DELIVERY.md) | Bank CSV preview/history, guarded raw access, validation and client steps |
| [Phase 3 discovery](PHASE_3_DISCOVERY.md) | Import sequence, existing boundaries and remaining business questions |
| [Phase 2.4 delivery](PHASE_2_4_DELIVERY.md) | Dated fees/timing/tax settings, preview, validation and client steps |
| [Phase 2.4 discovery](PHASE_2_4_DISCOVERY.md) | Confirmed fee/tax inputs, settlement questions and configuration scope |
| [Phase 2.3 discovery](PHASE_2_3_DISCOVERY.md) | Source-label evidence and accepted payment conventions |
| [Phase 2.3 delivery](PHASE_2_3_DELIVERY.md) | Editable source aliases, interpretation tests, validation and client steps |
| [Phase 2.2 discovery](PHASE_2_2_DISCOVERY.md) | Workbook category catalog and accepted business defaults |
| [Phase 2.2 delivery](PHASE_2_2_DELIVERY.md) | Editable taxonomy, inherited privacy, common initialization and client tests |
| [Phase 2.1 delivery](PHASE_2_1_DELIVERY.md) | Account/terminal configuration, validation and client test steps |
| [Phase 1 delivery](PHASE_1_DELIVERY.md) | Implemented access foundation, validation evidence, setup and client test steps |

These files are the canonical finance specification in the backend repository.
The frontend has a pointer in `docs/FINANCE_MODULE.md`. Update business definitions
here rather than maintaining conflicting copies in both repositories.

## Working agreement

The client defines business policy and accepts delivered behavior. The developer
owns implementation, technical choices within the accepted scope, validation,
and a useful handover. Ask focused questions at the beginning of each phase;
do not ask the client to decide routine implementation details. The client has
requested one consolidated numbered questionnaire at this checkpoint; use
QUESTIONNAIRE.md for the next answers instead of sending its questions separately.

1. Read this index, the current phase, and outstanding discovery questions.
2. At phase start, identify business decisions needed for that phase. Check
   existing answers before asking again. Ask a small batch of focused questions.
3. Record answers and their date in Discovery. Update Business rules and the
   decision log together; distinguish accepted decisions from proposals.
4. Implement one subphase at a time on corresponding backend/frontend branches.
   Progress on independent work while waiting for answers. Leave dependent
   business behavior pending instead of treating silence as approval.
5. Run checks appropriate to the changes, document results and limitations, and
   provide concrete client acceptance steps with expected outcomes.
6. Update Progress after each meaningful delivery. Record acceptance separately
   from implementation and automated validation.
7. Review the completed phase with the client before proceeding to the next
   phase, unless the client explicitly authorizes continuing across that gate.
8. Record approved changes to scope and their effects on dependencies and tests.

Use this response structure for delivery handoffs:

- **What I did:** completed work, behavior, documentation, branch, and validation.
- **What you should test:** environment, steps, expected outcomes, and outstanding
  business questions. For documentation-only work, ask for specification review
  and explicitly say that no application testing is available yet.

Use self-review and normal tests by default. An external review agent is optional
and is used only if the client asks for one. No external review agent is part of
this delivery plan.

## Development and release

Current branch in both repositories: `feature/finance-phase-2`.
Use a corresponding branch per subsequent phase, with smaller branches/PRs where
needed. Record actual branch names and commits in Progress; proposed names are
not evidence that a branch or commit exists.

Use staging and a finance feature flag for online acceptance once runtime work
exists. Keep production release and data migration as explicit delivery steps.
The old request to publish a purchase-matching fix does not authorize publishing
the finance module. Never include raw financial reports, credentials, or personal
customer data in Git. Do not modify unrelated existing work.

## Handover rule

A future developer should be able to identify the accepted rules, unresolved
questions, current implementation, test evidence, and next subphase from this
folder. Never mark a phase complete merely because its documentation exists.

Payment preview handover: [PHASE_3_3_3_1_DELIVERY.md](PHASE_3_3_3_1_DELIVERY.md).

Shared receipt/import handover: [PHASE_3_3_3_2_DELIVERY.md](PHASE_3_3_3_2_DELIVERY.md).
