# Phase 3.4 enriched historical migration discovery

Date: 2026-10-25. Phase 3.3.2 accepted (D-059). Q-015 answered (D-060–063). Phase 3.4.1 source previews implemented and validated;
client acceptance pending. Financial migration and complete-month pilot remain
unimplemented. See PHASE_3_4_1_DELIVERY.md.

## Purpose and accepted scope

Bring the existing enriched financial history into finance without losing manual
work or counting it again when routine raw reports overlap. The accepted pilot
approach is one completed Dominican month (D-045); September 2026 is selected (D-060).
The original September 1–15 bank/Alegra examples are partial adapter evidence.
Spain history remains in the agreed broader scope, after the Dominican pilot.

## Settled behavior to preserve

- BR-022–028 already define a distinct enriched import, recognizable workbook and
  column mapping, preview, independent valid-row continuation, preserved manual
  values, no blank erasure, explicit conflicts and retry-safe source provenance.
- Preserve bank transaction facts separately from business description, operation
  date, expense period, category/subcategory, studio, method, terminal and legacy
  review flags. Imported existing assignments count as manual decisions, not new
  automatic suggestions. No bank-verified balance is fabricated for cash.
- A legacy Conciliado flag preserves recognition/review only unless specific sale
  and deposit evidence reconstructs a match (BR-028). This is settled; do not ask
  for confirmation again or invent invoice-to-bank reconciliation.
- Existing bank and sales postings may already overlap the workbook. Link matched
  source evidence rather than create a second movement/sale. Genuine repeated
  equal-looking payments remain distinct; ambiguous rows require review. No date/
  description/amount unique hash or globally unique bank reference assumption.
- Bank source corrections retain current facts until explicit approval (D-050).
  Proposed imported manual changes also require review. Source/migration history
  must retain old evidence and actor decisions; a later blank does not erase work.
- Cash/manual entries retain their own origin/account context. A later matching
  bank occurrence requires linking/review rather than automatic duplicate creation
  (BR-035). Identify cash versus bank from evidence, never guess from description.
- Map locations to existing studios. Unknown configuration gets proposed/reviewed;
  no duplicate studios or silently invented categories. Common editable category
  codes, sensitive categories and administrative company costs remain as agreed.
  Administration is a shared-expense pool, not a fabricated operating studio.
- Existing own-account transfers stay internal: operating/savings or cash deposits
  do not become sales/expenses. Savings starts 0 DOP on 2026-01-01; migration of
  transfer evidence can later support expected balance without claiming a bank
  statement or verified counterpart exists.
- Alegra remains the DR sales source; workbook income receipts are not additional
  invoices/revenue. Spain remains on Mindbody. No inferred historical source
  cutover, month close, tax policy or refund policy is introduced here.
- Sensitive source access, company/account scope, finance import/edit permissions,
  stale-plan checks, audit and existing undo safeguards apply to migration too.
  No real files enter Git and no finance production migration is authorized.

## Q-015: questions sent

1. Which completed Dominican month should we use for the first migration comparison? I suggest September 2026 if you have finalized it. The bank/Alegra examples supplied so far cover only September 1–15, so those alone cannot validate a full month.
2. Is Ingresos_Egresos_DO_BI.xlsx still your current master workbook, or will you use a newer/different copy for migration?
3. How does the workbook distinguish manually added cash expenses from bank-paid expenses? Is there a column or label identifying the account/payment origin, or must you identify those entries manually?
4. Can one bank debit appear as several workbook rows because you split it between categories or studios? If yes, how do you identify those rows as parts of the same payment?

Questions 1–2 establish pilot evidence and source version. Questions 3–4 determine
account provenance and payment-versus-allocation structure; they do not reopen
manual-entry support or genuine duplicate preservation. Answers received below
(D-060–063).

## Proposed delivery sequence

1. **3.4.1 read-only enriched preview.** Inspect the confirmed source workbook's
   sheets/headers/formulas and populated coverage using read-only extraction.
   Map movement columns, identify account/provenance evidence and preserve original
   rows, values and any formula/cache issues. Preview counts and totals by actual
   bank date, operation date, expense period and studio where known. Summaries and
   result tables are comparison evidence, not additional movement rows.
2. **3.4.2 classification/provenance foundation and migration decisions.** Add the
   minimum assignment, period, cash/manual and allocation structures required to
   retain the actual legacy data, keeping broader Phase 4 review work bounded.
   Plan links to existing bank records and preserve manual assignments. Handle
   ambiguous identity, unknown config, conflicting assignments and split payments
   explicitly before financial commit. Do not flatten multiple allocations into
   duplicate bank payments. Exact split design depends on Q-015/source evidence.
3. **3.4.3 pilot posting and comparison.** Import the agreed period into isolated
   QA; preserve invalid/ambiguous rows for review and post independent valid rows.
   Compare original totals and classifications, rerun migration, then import an
   overlapping raw bank report. Exercise protected undo. Only claim the completed
   month comparison when complete source coverage and reference figures exist.

Each subphase receives tests, a client checklist and acceptance before advancing.
Preview/technical preparation may proceed independently, but source-dependent
cash/split interpretation cannot be treated as approved by silence. This design
is proposed sequencing, not evidence that new code/models/imports exist.

## Verification and open dependencies

- Required bank dates/amounts must validate; missing expense periods/assignments
  stay visible and are not guessed. Cross-month payment/expense examples must
  retain both dates. Preserve workbook text, manual dates and unknown labels.
- Distinguish cash entries, imported bank rows, shared administration and internal
  transfers. Preserve bank payment totals independently of allocation totals.
- Repeat/reordered migration and later raw overlap preserve occurrence counts and
  manual classifications. Existing financial postings remain intact.
- Privacy checks cover preview cells, originals, account choices, issue queues,
  history, commit and undo. Sensitive expense descriptions remain restricted.
- September 2026, unknown cash/bank origin and no legacy split rows are confirmed
  by Q-015. The current full saved workbook and second bank-report path remain
  pending. Phase 3.4.1 source previews are ready for testing; see the delivery
  checklist. Financial migration and complete-month certification remain future
  work. No production cutover date is inferred.


## Q-015 answers received — 2026-10-25

1. September 2026 is the Dominican pilot month. Client has bank reports for
   September 1–15 and 14–30 to test overlapping September 14–15 (D-060).
2. Client confirms Ingresos_Egresos_DO_BI.xlsx as the master and states it is updated
   through October 22 (D-061). The saved file at the previously supplied path was
   inspected read-only and remains a partial sample: 16 debit and 25 income
   financial entries dated August 31–September 2. It also has an incomplete
   classification-only debit row. Client's intended master coverage and observed
   local file coverage must be kept separate. The current saved master path/copy
   and 14–30 bank report path were requested asynchronously; no replacement path
   has been supplied at this checkpoint.
3. The workbook does not distinguish cash from bank-paid entries (D-062). Keep
   payment origin unknown; preserve source/manual fields and propose later
   matching/manual review. Do not infer an account from descriptions or balances.
4. One bank debit is not split into multiple workbook rows (D-063). No legacy
   split reconstruction is needed for this format. Future manual allocation
   support remains in Phase 4; genuine repeated movements still remain distinct.
