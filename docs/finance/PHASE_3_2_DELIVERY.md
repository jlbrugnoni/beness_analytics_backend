# Phase 3.2 bank transaction import, review and undo delivery

Date: 2026-10-24. Implemented and validated. Accepted by the client on
2026-10-25 (D-051).
Both repositories: feature/finance-phase-2. No production release authorized.

## What I did

- Recorded Q-012 yes/yes as D-049–050 and BR-056–057. Undo requires import/edit
  access and account/privacy scope. Financial committer owns the posting; settings
  authority additionally permits others' postings, without a force-undo bypass.
  Bank amount/date replacement requires explicit approval, with old evidence kept.
- Added Account.ledger_revision, BankPosting, BankMovement, BankDecision and
  BankEvent in finance.0007_account_ledger_revision_bankposting_bankmovement_and_more.
  Raw batches/rows/files stay immutable. A posting owns the financial decisions
  for one batch; movement source values are separate from their source occurrences.
  Fingerprints are indexed supporting evidence, never unique transaction keys.
- Added GET /api/finance/bank-imports/{id}/processing/ with paginated decisions,
  counts, ledger plan token, posting state and available actions. Added POST
  commit/, resolve/, undo/ plus GET undo-preview/ and activity/.
- Added read-only /api/finance/bank-movements/ with active/all/reversed state and
  per-movement history/. Histories identify their source batch. Import history
  now shows source parse status separately from financial processing status.
- Commit creates new movements, links recognized source occurrences, and stores
  invalid/pending review decisions without fabricated values. One source batch
  has one posting; repeat commit is idempotent. After undo, a fresh preview is
  required to import again. No raw file/row is deleted or reinterpreted.
- Review supports create distinct occurrence, retain current/link evidence,
  approve bank correction, or ignore with a note. It requires import/edit access,
  current plan/row/target revisions and same-account/provider active targets.
  Two rows in one posting cannot collapse into one movement. Reconciled movements
  cannot receive a bank-source replacement through this surface.
- Undo previews eligible/protected/reused records before confirmation. Only
  untouched, unreconciled creations with no other active import support reverse.
  Linked existing records remain. Approved source corrections are protected.
  Audit records and original files survive, and reversed movements remain visible
  under All/Reversed. No hard financial deletion is used.
- Partial undo freezes pending decisions for that posting. If independent import
  dependencies are later undone, a fresh undo preview can reverse newly eligible
  creations. Replaying an already-used undo request does not apply it twice.
  Source corrections or later edits are never forced back by this action.
- Company/account locks, ledger revision and row/target revisions guard commit,
  review and undo. Concurrent stale plans fail rather than create duplicates.
  Read/privacy gates from 3.1 protect ledger, candidates, raw files and history.
  Inactive/cash accounts cannot receive bank changes. An account with bank source
  history cannot be converted to cash through configuration.
- Added EN/ES import confirmation, decision table, explicit correction comparison,
  target lookup, reason fields, undo preview, active/reversed ledger and readable
  before/after history. Import-history processing status refreshes after actions.

## Matching rules and practical limits

- Exact same-file retries reuse earlier source-row occurrence links when those
  movements remain active and unchanged. An old file cannot silently revert an
  approved correction to that movement.
- Different files may automatically link a single exact source match when the
  incoming occurrence is unique and has balance/reference/serial evidence.
  Equal-looking repeated groups stay ambiguous unless source lineage resolves
  individual occurrences. First-time repeated rows create distinct movements.
- Matching references/serials, balance/context, and weak missing-identifier
  date/description evidence suggest corrections or identity review; they do not
  authorize replacements. References are not globally unique. New distinct IDs
  and differing balances can distinguish legitimate additional occurrences.
- Candidate detection is conservative but cannot prove every real-world identity.
  If date, amount, balance and references all change, there may be no shared
  evidence to identify a correction automatically. Users must inspect unfamiliar
  movements and source coverage. No fuzzy identity guess or missing-row deletion.
- Candidate menus show up to 50 suggestions; scoped transaction-ID lookup permits
  other explicit targets. Reason and version checks apply to manual decisions.

The plan/commit token depends on the account ledger revision; every supported
financial write advances it. Future classification/reconciliation writes must use
this locked/audited path, bump movement revisions and advance the account revision.
Do not bypass it with unaudited ORM/script changes. Reconciled flag is groundwork;
there is no sales-reconciliation UI in this phase.

Bank movements are bank-source records, not authoritative sales or profit.
Expense categories/periods, manual cash, administration allocation, terminal date
inference, invoices, fee adjustments and monthly results remain later work.
No new classification fields or net-profit/tax calculations are claimed here.
No closing locks were introduced. Historical migration and Alegra remain later
Phase 3 deliveries. Exact completed-month pilot selection remains deferred.

## What you should test

Use the existing isolated reviewer at http://127.0.0.1:3037/finance/imports.
Choose the intended account carefully; source-account ownership is still an
explicit selection, not an inferred bank-account-number match.

1. Open a successful preview and review Transaction import and review. Confirm
   Import transactions. Verify created/linked/pending counts and expand Account
   transactions and history. Invalid/ambiguous rows must not stop independent
   valid new rows. A failed file-wide parse cannot be imported.
2. Save/review an overlapping or identical file. Recognized rows must link instead
   of duplicate; genuinely repeated source rows must remain separate or pending
   explicit identity review. A repeated commit must not create extra records.
3. For a proposed bank correction, inspect current versus reported date/amount.
   Approve it with a reason or keep/ignore the new evidence. Transaction history
   must retain the previous values. Independent new rows can already be present.
4. Preview undo. Confirm eligible/protected/reused counts before executing with
   a reason. Reused and protected movements remain. Use All/Reversed to inspect
   reversals. Managers have no force-undo shortcut. Ownership is financial
   committer, not necessarily the original raw uploader.
5. A stale plan should request reload instead of applying outdated decisions.
   Read-only users should not see enabled import/review/undo controls without
   their required capabilities.

Developer browser tests used only dedicated synthetic account
Posting QA - Popular (DOP), preserving pre-existing user-uploaded QA previews.
Its source batches: #9 base (two transactions); #10 repeated source (linked then
undone, original transactions retained); #11 proposed amount correction plus one
new transaction (correction explicitly approved, then partial undo reversed only
that new transaction). Remaining active synthetic movements: 110 DOP and -20 DOP.
These are QA examples, not real financial results. Original real previews remain
available for client testing; this agent did not post them.

## Validation / release notes

- Final PostgreSQL 16 suite: 217 tests passed (136 finance/access/config/import,
  81 existing analytics/purchase/import regressions). New posting coverage is
  19 tests, including two real PostgreSQL concurrent-import races.
- Focused SQLite run before the last account-history guard: 16 ordinary cases
  passed, two PostgreSQL races skipped. The final extra account guard and history
  assertions are covered by the PostgreSQL run; no claim 19 SQLite cases passed.
- Django check and makemigrations --check --dry-run clean. Frontend lint/build
  passed with existing unrelated warnings; no new finance lint warnings.
- Browser: new commit, repeated-file linking, undo of reused evidence, independent
  new row alongside correction, explicit correction approval, 100->110 history,
  partial undo (new transaction only) and active ledger counts verified.
- Test/build logs: /private/tmp/finance-phase3-2-{focused,pg-tests,lint,build}.log.
  Browser proof saved in /private/tmp/finance-phase3-2-transaction-history.png.
- The previously documented legacy core_data.tests imports removed Center. The
  supported regression modules above pass; this is not a claim all legacy test
  discovery is healthy. No external review agent was used.

Only isolated QA/test databases migrated. The synthetic reviewer gained edit
capability and a dedicated synthetic bank account for this phase. No real user
grants or normal/production DB changed. Existing QA uploads were retained; no
real financial movements were created by the agent. No source reports or
credentials committed; unrelated exports/ untouched. No push/merge/deployment.
Apply migration 0007 before updated backend traffic, even with finance hidden.
Back up the full database, including retained source bytes, before any authorized
release. QA frontend 3037/backend 8027 remain the local testing surface.

Next gate: client acceptance, then Phase 3.3 Alegra invoice/item import discovery.

Phase 3.2 implementation checkpoints: backend `8de1698`, frontend `7a343fd`.
