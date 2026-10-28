# Bank matching and accessible pending review — D-088

Delivered 2026-10-27 local date on `feature/finance-phase-2` in both repositories.
Development only; no merge, push, production deployment or working-data reset.

## Accepted behavior

Compare within the same account/provider and currency/direction. The primary bank
facts are original transaction date, signed amount, description and reported balance.
Use the original bank date, not the independently assigned operation date.
Collapse whitespace for comparison only; retain original source values.

- Exact uniquely recognized overlaps link to existing transactions. Additional missing
  metadata can support the same four facts; conflicting nonempty reference/serial
  metadata still requires review instead of silently replacing source facts.
- Equal date/amount/description with different known balances represents separate
  occurrences. The same terminal may have several settlements on the same day.
- Missing balances and indistinguishable occurrences remain reviewable when identity
  is uncertain. Known same-file row-to-movement evidence remains usable; a repeated
  upload does not needlessly lose its established occurrence identities.
- Popular serial is not an independent identity anchor: it can identify a terminal or
  recurring party. Generic references0/1 (including zero-padded forms) are also not
  identity anchors. A meaningful reference or shared transaction balance can still
  expose a possible source correction; it does not silently approve that correction.
- Preserve repeated occurrence counts. Multiple incoming rows cannot automatically
  claim one existing movement. Existing confirmed links/creations/ignored/corrected
  decisions remain in force, and a movement already used in the posting is protected.

Plan token advances fromv3 tov4, invalidating previews made under the old matcher.
No model/schema migration is introduced. Existing business classifications are not
reset by routine bank overlaps.

## Daily UI

Upload reports → select company/bank/account → Upload history → Open report →
**Review pending**. This button is directly beside the pending count, independent of
the advanced import-history page. The dialog lists unresolved rows only, with dates,
descriptions, amounts, balances and current matching results, with pagination.

**Apply ready rows** opens a confirmation showing the global counts of new and
already-present rows. It adds unambiguous new transactions and links recognized
overlaps; genuine conflicts remain pending. It is available only with existing
import/edit permission and complete bank/sensitive/account scope.

For an individual conflict, **Review transaction** shows incoming/existing bank facts
side by side. Choose an existing candidate to inspect highlighted differences; no
candidate or decision is selected automatically. Decisions:

1. Already recorded → link existing; retain the original and its classifications.
2. Separate transaction → add new.
3. Source changed → explicit protected source correction, with required reason.

Create/link decisions do not require typing repetitive notes; the backend records
the actor and a standard explanation. Source corrections and ignored rows still need
a reason. Manual/reconciled source protections and stale-revision checks remain.
The advanced review/history/undo page remains available.

## API and transaction protection

- GET `bank-imports/{id}/processing/` adds `pending_count` and `ready_counts`.
- `?pending=1` returns only pending rows; counts remain global to the report.
- POST `bank-imports/{id}/apply-pending/` accepts a fresh `expected_plan` token.
  It recalculates under company/account locks, processes only current pending new/
  unchanged rows, and uses the existing audited resolver for each decision. It does
  not change earlier resolved decisions or automatically correct source facts.
- A stale retry fails409. A refreshed retry with no ready rows changes nothing.
  All operations are in one transaction, so a later failure rolls back the batch.
- Individual `resolve/` permits omitted/blank notes for create/link, assigning the
  standard audit explanation; correction/ignore still reject blank reasons.

## Validation

322 PostgreSQL finance tests passed, including11 new matching/recovery regressions.
Coverage includes recurring terminals/parties/generic references, distinct same-day
balances/amounts, missing balances, metadata variants/occurrences, recovery preserving
earlier work, stale/repeat submissions, permission revocation and explicit source
corrections. Two older tests were aligned with the agreed behavior: shared serial or
description alone cannot make a different amount/balance a correction; a shared
transaction balance still retains a source-change review case.

Frontend changed-file lint and production build passed. No migration drift.
Browser checked real report21's pending85/new85/recognized0 preview and its confirmation
without applying it; checked report20's side-by-side20,000DOP source conflict and
disabled source-correction confirmation with a blank reason. No real decisions were
submitted during browser verification.

## Real-data rehearsal in a disposable copy

Consistent SQLite backup via the SQLite backup API, private temporary directory:
`finance-popular-v4-7h9b8qcw/sandbox.sqlite3` under the host's temporary directory.
`rehearsal.json` in that directory records the result (not a production backup).

Normal recovery API for report21 added85 movements, cleared its pending queue and
preserved every one of the525 existing movements/classifications,1214 invoices,
1219 payments,6 daily checks and8 check events. Only the85 originally pending
decisions changed; the53 existing links and32 creations retained their decisions.
Stale retry returned409; fresh retry was a no-op. A new upload of the exact original
CSV recognized all170 rows; committing it created0 movements.

Working report21 remains pending85, ready to be exercised by the client. Working
report20 still has8 recognized pending links plus2 substantive description conflicts.
No financial data, import decisions, manual entries or grants were changed by this
delivery in the working database.

## Client acceptance

1. Open report21 through Upload reports and Review pending. Expect85 new and0
   already-present rows ready. Apply ready rows and confirm. Expect no pending rows
   for this report; existing classifications/53 overlap links stay intact.
2. Preview/re-upload the same report: expect170 recognized rows and0 new movements.
3. Inspect report20's remaining source differences. Apply its8 recognized rows if
   satisfied; its2 description conflicts must remain for individual decisions.

Do not undo/reset the existing dataset to test this recovery. Full September monthly
comparison, real-partner acceptance and production cutover rehearsal remain release
gates in DR_OPERATIONAL_RELEASE.md.
