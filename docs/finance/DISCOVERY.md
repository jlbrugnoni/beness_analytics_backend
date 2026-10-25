# Finance discovery questions

Updated: 2026-10-25. Ask focused batches and attach answers to stable question IDs.
Do not turn a suggested answer, elapsed time, or lack of reply into a decision.

Current response format: the client requested a single numbered list. See
[the consolidated questionnaire](QUESTIONNAIRE.md), issued 2026-10-24. Record its
answers against the original topics below and extend the register for new
migration, taxonomy, closing, and tolerance decisions. Do not resend its questions
as separate asynchronous prompts. The client answered all 12 on 2026-10-24;
the questionnaire's answer register records them and three focused clarifications.

## Phase 0 first batch

The following three questions were sent to the client on 2026-10-24.
Answers received on 2026-10-24 are recorded below. Each is partially answered;
follow-ups and their answer status are recorded below.

### Q-001 Company and account ownership

The Dominican reports name Beness Pilates Studio S.R.L. What legal entity owns
the Caixa account in Spain? Are there additional bank or cash accounts in either
country to support initially?

Needed for company/account/currency context. Record owner, country, account label,
currency, and participating studios. Do not request bank credentials.

Answer (2026-10-24): "Bewellness Group SL".

Accepted interpretation: Spain's Caixa account belongs to Bewellness Group SL.
The Dominican report identifies Beness Pilates Studio S.R.L. The client also
described Dominican operating-to-savings transfers in Q-002. See D-007/BR-003.

Consolidated answer 1 (2026-10-24): define Dominican Republic first and recommend
a name such as general account. Selected label proposal: Banco Popular - Cuenta
operativa (DOP), under the Dominican company. Other bank/cash accounts and studios
remain editable setup; no extra real account or opening balance has been created.
This is enough to design configuration without requesting a complete inventory.

### Q-002 Cash lifecycle

When cash is deposited into the bank, has it already been recorded as cash sales
in Mindbody/Alegra? How are cash expenses and money kept at the studio recorded?

Needed to distinguish sales, cash account movements, deposits, and petty cash
expenses without double counting.

Answer (2026-10-24): cash deposited should already be recorded as sales. The client
requested a category or flag for internal movements. Dominican operations also
transfer money from the operating account to the savings account at month end;
these movements must be taken into consideration in the final result table.

Accepted interpretation: model internal movements explicitly and preserve the
source movements. Check existing cash sales rather than assuming every deposit
is new income. Support savings accounts even if transaction volume is low.
See D-008/BR-014.

Follow-up answer (2026-10-24): "Yes, separate movements; exclude principal from
profit". P-001 is accepted: show own-account transfers/cash deposits separately,
exclude principal from income, expenses, and profit, and retain associated fees
as expenses. See D-010/BR-014.

Consolidated answer 2: cash/other expenses are typed manually. V1 supports manual
creation and report uploads, with visible manual/import origin and report name.
See BR-035. Verified cash balances/opening balances have not been requested by
this answer. "Should already be recorded" does not prove every historical cash
deposit has corresponding sales.

### Q-003 Processing fees

Should monthly results use estimates, actual fees, or estimates until actual fees
are available? Are separate AZUL debit charges additional to the percentages
withheld from deposits?

Needed to distinguish withheld processing fees, separately charged fees, estimates,
and later adjustments. A selected overall fee policy does not answer the AZUL
charge question by itself.

Answer (2026-10-24): outgoing transfers and other operations can have fees. An
AZUL card deposit already has processing fees subtracted. The Excel closures
subtract a channel-specific commission from Alegra invoices before comparing
against the bank deposit.

Accepted interpretation: expected net collection = gross sales less configured
processing fee; bank amount is already net. Separately charged fees are distinct
movements. See D-009/BR-019.

Follow-up answer (2026-10-24): "Yes, estimates with later adjustments". P-002 is
accepted: deduct configured estimated processing fees from gross sales, count
distinct bank charges as expenses, and adjust estimates when actual fees become
available. See D-011/BR-019. Do not add the whole actual fee on top of its estimate.

Consolidated answers 5–6: unidentified AZUL debits stay for review. Caixa has a
first-year terminal offer: a fee debit is followed by a separate reimbursement
credit. Retain both and classify a linked reimbursement as fee offset, not sale
or internal transfer. Do not assume eligibility on every date; configure offer
dates and preserve unmatched issues. BR-039. Historic spreadsheet rates remain
reference configuration, not proof of every actual charge.

## Follow-up batch sent on 2026-10-24

1. Q-002: confirm separate display and profit exclusion of own-account principal,
   while associated fees remain expenses.
2. Q-003: select monthly fee policy: estimates with later adjustments, actual fees
   only, or estimates without adjustments.
3. Q-001: list the initial bank/cash account labels and currencies.

Current status: original and consolidated business batches are answered. Q-001
uses DR-first configurable setup; cash is manually entered with provenance;
unknown AZUL fees stay for review; group/user permissions and sensitive categories
are defined; allocation, tax-inclusive results, refund timing, final result, and
Spain's initial source are settled. Detailed source and configuration validation
continues in the relevant implementation phases.

## Remaining Phase 0 topics

Question-specific status is recorded below.

### Q-004 Access matrix

Define initial roles and grants, full-company versus studio access, source-file
and shared-account visibility, any extra restriction on payroll/customer detail,
who grants permissions, and the explicit technical-superuser exception.
Ask at the latest before Phase 1 authorization work depends on them.

Sent on 2026-10-24: proposed Finance Manager, Finance Operator, and Studio Finance
Viewer roles; asked which are needed, who assigns them, whether studio managers
can edit/reconcile, and whether payroll needs additional restrictions.

Answer (2026-10-24): the app is internal for partners. Keep the existing style of
user groups, allowed sites, money visibility, and permissions. Add individual
permissions or make group capabilities selectable; the client delegated which
approach is best to the developer.

Selected technical approach: editable group capability sets plus additive user
grants, using existing location limits. Groups are the usual source of grants;
direct user grants cover exceptions. Preserve the existing OR combination model
and explain inherited permissions in the UI. V1 does not add separate finance
role grants or per-user deny semantics. See D-012/BR-029–031.

Money visibility alone is insufficient for finance; explicit finance capabilities
are required. Reuse current user-management authority for capability/group edits.
The backend already supports editable GroupAccessProfile records; add the missing
frontend group capability editor instead of inventing another group system.

Consolidated answer 10: use sensitive/private category flags and an extra
permission to restrict specific salary items/descriptions while keeping totals.
Selected design: aggregate-only sensitive category data without the extra
capability; protect all detail paths and raw downloads, not only descriptions.
See BR-037. Developer-selected technical policy: Django superusers retain full
technical administration; ordinary Admin group membership alone does not create
finance grants. No live grants or capability code have been implemented.

### Q-005 Allocation and movement treatment

Define how shared expenses are split, what internal transfers represent, and how
loans, owner contributions/withdrawals, refunds, and extraordinary items affect
the management result. Ask targeted follow-ups using client examples.

Initial shared-expense question sent on 2026-10-24: how are company-wide costs
such as administration/software currently allocated—company overhead, percentages,
or another rule? Requested one example to establish the first-version behavior.

Answer (2026-10-24): company-wide expenses are normally classified as administration;
later, administration expenses are assigned to each studio by weighted income.

Follow-up answers (2026-10-24):

1. Income weights use "Gross sales before processing fees".
2. "Yes, use the expense month; leave pending if no income"; the question included
   a manual split as the alternative for months with no income.

Accepted interpretation: retain the company-wide administration source expense
and allocate using each studio's gross-sales share for the expense month. A cost
paid in September and assigned to August uses August sales. Zero-income months
remain pending with a manual split available. Preserve source/allocated detail
without counting the cost twice in company totals. See D-013/D-014/BR-032.

Do not infer that every administration-category row is shared if historical data
already assigns it directly to a studio. Refund/non-positive income edge cases,
rounding, and recalculation after source changes need detailed specification
before allocation implementation. Consolidated answer 8 chooses original sale
month for refunds; record linked adjustments and actual refund dates separately
(BR-038). Consolidated answer 9 puts financing, large equipment, and tax payments
outside operating result, with extraordinary effects shown in final result.
Follow-up sent: confirm final result = operating + extraordinary inflows -
extraordinary outflows, and distinguish which tax-related payments are operating.

Follow-up answers received 2026-10-24: final formula/loan example accepted. Only
revenue-related taxes are non-operating; employment taxes remain operational.
Map actual tax categories during setup; no treatment is inferred for unidentified
bank transaction taxes. See D-022/BR-020.
Do not call the custom management measure EBITDA without separately defining it.
Own-company internal principal remains covered by D-010.

### Q-006 Result basis and Spain sales

Confirm gross/net tax presentation and the current Mindbody sales report used for
Spain, including payment date, paid total, refunds, and split payments. Verify
whether the required source is already imported before requesting another file.

Tax question sent on 2026-10-24: should monthly sales and expenses include
IVA/ITBIS, or should taxes appear separately, and does policy differ by country?

Answer (2026-10-24): Spain sales include 21% tax. The Dominican activity has no
sales tax. The client requested an editable configuration field.

Accepted interpretation: company-level configurable default tax rate/treatment,
inclusive-price flag, effective dates, and original source totals preserved.
Record these as client-provided setup, not externally verified legal conclusions.
Explicit source tax and reviewed exceptions must remain traceable. See
D-015/BR-033.

Follow-up sent on 2026-10-24: confirm monthly presentation of Spain sales excluding
IVA, with IVA separately and the full paid amount used for bank reconciliation.
Illustration: EUR 121 = EUR 100 sales + EUR 21 IVA. Alternative offered: retain
tax-inclusive sales in the monthly result.

Follow-up answer (2026-10-24): the client prefers a basic result including IVA
because some expenses include IVA and others do not. Expense tax can be added
later to enable comparison of net amounts with net amounts.

Accepted v1 scope: use sales including IVA, recorded full expense totals, and
tax-inclusive gross sales before fees for administration weights. Preserve tax
configuration and explicit source metadata; do not require complete expense-tax
capture or a net-of-tax result in v1. Label the result basis. The earlier
excluding-IVA presentation was a proposal and is not the selected v1 behavior.
See D-016/BR-034.

Deferred: expense-tax capture, recoverability policy, and consistent net-of-tax
results. Do not apply a 21% sales default to every expense. V1 tax presentation is
resolved. Consolidated answer 7: Mindbody Sales is current Spain source for date
precision; Alegra is preferred for both countries after process improvement.
Spain's consumer invoices may have no client name, unlike commercial invoices.
Follow-up sent: use Mindbody initially or Alegra from start, and what cutover if
historical/later periods differ? Validate a Spain Alegra export before acceptance.
Consumer invoices must not fail because customer name is absent. See BR-008.

Follow-up answer received 2026-10-24: use Mindbody for Spain for now. V1 sources
are settled: DR Alegra, Spain Mindbody Sales. No cutover date or second routine
Spain sales upload is required. Later Spain Alegra adoption needs source
validation and an explicit cutover.

## Other consolidated answers

- Answer 3: DR historical coverage starts January 2026; Spain expenses mid-2025,
  sales February 2026. Flag incomplete/expenses-only periods (BR-036).
- Answer 4: initial workbook taxonomy remains editable through the app (BR-002).
- Answer 11: month closing prepared for later, not enforced in initial use
  (BR-021). Reopening/strict locks are future features, not a new v1 gate.
- Answer 12: developer-recommended 0.01 DOP/EUR rounding-review threshold; no
  automatic write-offs or confirmation of nonzero differences (BR-040).

## Q-007: Phase 2 accounts, terminals and fees

Asked 2026-10-24 as a consolidated numbered list following Phase 1 acceptance.

1. Client accepted operating/savings labels, explained savings statements are
   unavailable and requested its expected balance. Follow-up: "we initialized
   the year with 0 balance"; migration contains internal transfers. Record the
   reference at start of 2026-01-01 based on confirmed 2026 DR history (D-028).
2. Supplied eight DR terminal mappings, preserved exactly in
   INITIAL_CONFIGURATION.md (D-029). Terminal data is configuration, not source
   financial transactions. No unprovided mapping should be inferred.
3. Confirmed 3.5% Cierre and Recurrentes, 5% Link. Follow-up: rates have applied
   "since forever"; use historical baseline rather than inventing a start date
   (D-030). Fixed charges were not supplied.

No further answer is needed for accounts/terminals development. Savings expected
balance engine and fee calculation are explicitly later work.

## Q-008: Phase 2.2 category setup

Sent 2026-10-24 after Phase 2.1 acceptance (D-031). Extracted only category
labels and counted debit category pairs from the existing workbook, read-only.
PHASE_2_2_DISCOVERY.md records source ranges, all 44 catalog pairs, helper-list
variations and pending questions on company ownership, sensitivity, treatment and
catalog initialization. No original source workbook was modified.

Answers received 2026-10-24: independent catalogs accepted, with the intent to
use consistent categories across all companies for comparable analysis; proposed
sensitive flags, result defaults, and catalog cleanup accepted. See D-032–035.
No additional Phase 2.2 question remains pending.

## Q-009: Phase 2.3 payment/studio mapping setup

Sent 2026-10-24 after Phase 2.2 acceptance (D-036). Inspected only mapping labels
from the original Alegra export and existing PaymentMethod/SaleLine integration.
PHASE_2_3_DISCOVERY.md records the source-field distinction and accepted studio
rules. Asked whether generic Alegra card labels also cover Link/Recurrentes,
whether cash/transfer labels can be trusted directly, and for Spain Mindbody
method names if available. Spain aliases can remain unconfigured while generic
configuration/DR work proceeds. Client answers received 2026-10-24: debit = Link, credit = Cierre, cash = cash,
transfer = transfer; recurring also appears as credit and needs manual separation.
Spain initially uses in-studio card and cash, with no recurring or transfer.
Exact Mindbody labels remain unspecified and unseeded. See D-037–038. No further
business answer blocks this editor/preview subphase.

## Q-010: Phase 2.4 fee and settlement setup

Sent 2026-10-24 after Phase 2.3 acceptance (D-039). See
PHASE_2_4_DISCOVERY.md and QUESTIONNAIRE.md for the numbered questions.
The earlier Caixa answer confirmed a charge and reimbursement, but did not
explicitly settle whether each card deposit arrives gross or net. Fee amounts,
offer dates and channel-specific payout timing remain unspecified.
Answers received 2026-10-24: Caixa full deposits with independent refunded fee;
approximately EUR 36 and offer ending in 2027, without exact amount/frequency/dates.
DR normally 24–48 hours, sometimes longer on weekends. See D-040–041.
Unknown Caixa terms stay optional setup follow-up; no configuration blocker remains.
Existing DR rates and tax presentation are not reopened.

## Q-011: Phase 3 import and historical migration workflow

Sent 2026-10-24 after Phase 2.4 acceptance (D-042). See PHASE_3_DISCOVERY.md
and QUESTIONNAIRE.md for the four numbered questions. Existing operational
imports were inspected for integration boundaries, without reading new reports
or changing data. Answers received 2026-10-24 (D-043–046): Popular normally daily and potentially
overlapping; Caixa every several days; all Alegra invoices downloaded. Completed
DR-month migration pilot approach and proposed audited undo accepted. The exact
pilot month/cutoff and detailed source-update reversal cases remain later
phase-specific work. No further answer blocks bank-preview infrastructure.

## Q-012: transaction commit, source correction and undo authority

Sent 2026-10-24 after Phase 3.1 acceptance (D-048). Existing D-046 sets undo
record safeguards, but does not identify who may undo another user's upload.
Source history/manual preservation is settled; the exact amount/date replacement
approval path remains to be defined. See PHASE_3_2_DISCOVERY.md and QUESTIONNAIRE.md.
Client answered yes to both recommendations on 2026-10-24 (D-049–050).
Own/manager undo authority and explicit source-correction approval are accepted. These questions do not reopen
permission inheritance, scope, missing-row deletion or valid-row continuation.

## Q-013: Alegra invoice/item imports

Sent 2026-10-25 after Phase 3.2 acceptance (D-051). See
PHASE_3_3_DISCOVERY.md and QUESTIONNAIRE.md for the single numbered batch.
Questions cover numbering reuse/series, approval of complete corrected invoices,
split payment evidence, and cancellation/credit-note export behavior. Answers
received 2026-10-25 (D-052–055); exact cancelled-status text remains pending. Do not reinterpret absent invoices as cancellations or automatically
replace current items/status without the accepted approval safeguards.


### Q-013 answers received — 2026-10-25

1. Full invoice codes should not repeat within either company. Dominican series
   begin B01/B02 followed by eight digits. Keep company/source/full code identity,
   including prefix, rather than year-based reuse (D-052).
2. Yes to approval of changed source evidence, but Alegra currently allows only
   cancellation, not edits to invoice date, amount or client. Treat such changes
   as anomalies, retain the original and require investigation rather than offering
   ordinary edits to those values. Cancellation/status approval remains a later
   posting workflow (D-053).
3. No mixed payment methods in the current workflow. One or two cards can fund one
   invoice at the same moment; bank settlement is the whole day's card deposit.
   Do not require a split per card or assume card count changes invoice totals
   (D-054). Partial/grouped settlement matching remains Phase 5.
4. Cancelled invoices remain in the export with a cancellation status. The refund
   happens later as a bank debit. Preserve both events, remove the sale's result
   contribution in its original month and do not deduct the same refund twice
   (D-055, BR-038). Exact cancellation text in ESTADO is still pending: the sample
   contains only Cobrada. A focused asynchronous question requests that text.

First delivery: Phase 3.3.1 source previews. Invoice posting, approval of changed
statuses and refund reconciliation follow after preview review. This subdivision
keeps unconfirmed cancellation labels from being guessed.

## Q-014: sales posting and cancellation settlement

Sent 2026-10-25 after source-preview acceptance (D-056). See
PHASE_3_3_2_DISCOVERY.md and QUESTIONNAIRE.md. Two questions: exact cancellation
ESTADO text (carried forward, still unanswered), and whether cancelled/reissued
invoices can retain payment without a refund. Answered 2026-10-25 (D-057–058). Original-sale-month
refund treatment and explicit approval of posted status changes are already
settled; these questions do not reopen them.


## Q-014 answers received — 2026-10-25

1. ESTADO uses **Anulada** (D-057). Recognize Cobrada as paid and Anulada as
   cancelled, with normalization for case/whitespace. Do not guess other statuses.
2. Yes, invoices may be cancelled/reissued without refunding the client (D-058).
   Cancellation alone does not prove a refund is owed or paid. Keep settlement
   pending until an operator records refund expected, no refund, or a replacement
   invoice in the same company. A note is required. Do not create a bank movement
   or second profit deduction from that choice. Original-period treatment remains
   BR-038; refund-to-bank matching remains Phase 5.

## Recording an answer

Keep the question, append the client's answer with its date, state the accepted
interpretation, and link the resulting decision/rules. If an answer is partial,
identify only the remaining ambiguity. Update dependent phase tasks and progress.
