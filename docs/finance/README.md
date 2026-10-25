# Finance module handover

Status: Phase 0 accepted; Phase 1 accepted; Phase 2.1 accepted; Phase 2.2 accepted; Phase 2.3 accepted (D-039); Phase 2.4 implemented and validated; client acceptance pending. Updated: 2026-10-24.

The finance module will support bank imports, sales reconciliation, expense
classification, historical migration, and monthly management results for the
Dominican Republic and Spain. The client has accepted the overall direction.
The main discovery batch is answered. Finance foundation/access and account/terminal/category/source-mapping/fee/timing/tax configuration code and
migrations now exist; financial processing is still planned. See the Phase 1 delivery for
implemented behavior, checks, setup, and acceptance steps.

## Documentation index

| Document | Purpose |
| --- | --- |
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
