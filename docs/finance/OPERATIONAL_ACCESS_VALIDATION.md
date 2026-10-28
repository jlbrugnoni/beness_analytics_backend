# DR operational finance: closure access validation

Date: 2026-10-27. Branch: `feature/finance-phase-2`.

The client accepted daily checks and requested the completed history presentation
refinements. This follow-up verifies access to those checks before real-period
acceptance. It does not certify production profiles or complete September coverage.

## Verified behavior

| Scenario | Expected and tested result |
| --- | --- |
| Full company viewer with money, finance, bank and sensitive-detail access, without reconcile permission | Can read comparison and history; cannot check or reopen; UI capability is false. |
| Reconciler with those visibility grants and site scope | Can check and reopen. Existing user/group capability resolution applies. |
| Reconcile granted by an existing group rather than the user flag | Reopen succeeds and records the actual acting user. |
| Any one of money, finance, bank visibility or sensitive-detail permission removed | Comparison, evidence, history, check and reopen denied. |
| Site grant removed | Company comparison/history and writes return not found. |
| Partial studio restriction, even with visible studio accounts | Company-wide comparison/history and writes return not found. A studio filter is not an access grant. |
| Request company ID changed to a company outside allowed sites | Reads and writes return not found. |
| Finance feature disabled or user inactive | Reads and writes denied. |
| Company inactive | Existing authorized history remains readable; check/reopen rejected and capability is false. |

Denied requests leave checks and events unchanged and do not expose the stored
review note. History responses use `Cache-Control: private, no-store`.

These tests exercise real API endpoints with disposable users/groups/records in a
separate PostgreSQL test database. They do not grant permissions to working users.
The current full-company sensitive-detail gate remains unchanged; more granular
studio-only closure history is not introduced in V1.

## Validation result

20 tests passed: `finance.test_closure_access` (7),
`finance.test_operational_checks` (5), `finance.test_closures` (8).
No production behavior, schema or working financial records changed in this increment.

## Owner acceptance still required

Verify representative real partner profiles using their existing permissions:

1. An authorized viewer can inspect closures/history but has no check/reopen action.
2. An authorized reconciler can check/reopen within the intended company.
3. A user without finance/money access cannot enter finance; a restricted company or
   studio user cannot open another company's comparison or history by a direct URL.

Do not broaden access merely to complete testing. If a profile needs a new grant,
the owner chooses that change through existing user/group administration.

Remaining release gates are in [DR_OPERATIONAL_RELEASE.md](DR_OPERATIONAL_RELEASE.md):
real report overlaps, both Alegra arrival orders, complete-period comparison, source
identity decisions, recovery acceptance and production cutover rehearsal.
