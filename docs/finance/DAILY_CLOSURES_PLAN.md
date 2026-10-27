# Daily closures — phase discovery and delivery plan

2026-10-27. Status: discovery begun; implementation not yet delivered.
Predecessor: general money ledger delivery accepted by client (D-084).

## Client acceptance and scope

Client reports that the records match their documents and that they created manual
entries successfully. Accept the general money/cash workflow based on this review.
This is client acceptance of that workflow, not an independent certification of
all source records or completion of reconciliation/monthly results. Preserve their
manual entries and existing imports; no reset or cleanup is authorized.

## Purpose

Provide the daily comparison the client currently performs in Excel: authoritative
sales/payment evidence versus actual money received, including manually recorded
cash. An invoice payment is sales evidence; it does not create an actual cash entry.

## Existing decisions to reuse

- Group comparisons by operation/payment date, studio and assigned payment method.
  Keep bank transaction date distinct from operation date.
- Use Alegra invoice items plus Alegra transaction payments together for DR. Items
  provide invoice totals/studio; payments supply collection amounts, split methods
  and dates. Do not sum invoice totals repeatedly for each payment or item.
- Spain currently uses Mindbody as authoritative sales evidence; do not substitute
  Alegra or silently present missing Mindbody integration as zero sales.
- DR terminal/recurring withholding is3.5%, payment-link withholding5%, using
  effective-dated configured policies. Caixa currently deposits gross card proceeds;
  separate terminal charges/reimbursements do not reduce the expected card deposit.
- Cash expected receipts have no terminal withholding. Actual cash is entered
  independently. A later cash deposit is an internal movement, not another receipt
  from a customer.
- Keep customer-paid tax-inclusive amounts for this initial comparison.
- Exclude internal principal transfers, extraordinary inflows and expense-fee
  reimbursements from ordinary customer collection totals. Keep them visible as
  excluded records rather than silently dropping them from the ledger.
- Partial classification, Reviewed and Reconciled remain distinct. A zero difference
  is a comparison result, not an automatic confirmed reconciliation.
- Existing BR-040 applies:0.01DOP/EUR rounding-review threshold, retain exact
  differences and require explicit confirmation of nonzero differences. No automatic
  write-off, source amount modification or silent reconciliation.
- Cancellation/replacement/refund cases require their existing source decisions;
  do not double-reduce cancelled sales and bank refunds. Unknown treatment remains
  a review blocker, not an assumed completed refund.
- Settlement timing is suggestive, never an automatic hard date cutoff. Missing
  operation date/studio/method stays in an explicit unassigned queue.

## Questions awaiting client reply

1. Confirm the proposed main table: operation date + studio + payment method, with
   gross sales, estimated fees, expected receipts, actual receipts and difference,
   plus source detail on click. This presents the already accepted comparison basis.
2. Permit splitting a bank deposit across several operation days, preserving its
   original amount and requiring allocations to sum exactly to that amount?

An initial third question about tolerances was withdrawn after finding BR-040;
retain that established decision rather than reopening it.

## Proposed subphases

### C-1: Read-only daily comparison

Add a simple Closures page beside Records and Upload. Select company, dates, studio
and payment method. Show the comparison table, exact monetary values and drilldowns
into invoice/payment and actual-receipt evidence. Show missing assignments, missing
fee policies, unlinked receipts, cancellation decisions and incomplete source coverage
as actionable review states. Include unreviewed-but-assigned entries transparently;
do not silently hide them or imply the source period is complete.

Start with DR's existing invoice/payment adapters. An unsupported authoritative
source must be reported clearly; Spain's Mindbody bridge must be implemented and
validated before claiming a Spanish comparison is complete. Make missing data
unknown/incomplete, not a fabricated zero or a success badge.

Resolve effective fee policies and flag ambiguity/missing configuration; estimates
must be labelled. Record the rounding basis explicitly and test examples against
source evidence before relying on differences for reconciliation.

C-1 is read-only. It does not set reconciled flags or change invoices, payments,
manual receipts, classifications or historical source values.

### C-2: Explicit allocation and reconciliation

After client confirms deposit splitting, add saved links/allocations with decimal
amounts, source revisions, actor/time, confirmation note when required and audit
history. Support many invoice payments per collection group and many actual receipts
per day. Require both sides' allocated totals to conserve their original amounts;
prevent reuse/over-allocation, stale edits and concurrent double allocation.

Expose reconciliation and reversible unlink/reopen through normal permissions.
Protect reconciled records from source changes and manual edits; changed evidence
must enter a review/reopen flow. Never use a boolean alone as the matching model.
Exact-match suggestions still require explicit confirmation.

### C-3: Exceptions and source integration

Handle delayed/multi-day settlements, partials, processing-fee estimates versus actual
charges, refunds/replacements and unknown dates without forced matches. Complete and
validate the Mindbody adapter for Spain with the same comparison interface.

### C-4: Acceptance, then management results

Client compares selected August/September days and methods to Excel, including cash,
split invoice payments, missing assignments, internal deposits and refunds. Test
changes in either source and reopening before advancing to monthly results.
No reset is needed for these steps. The recoverable clean-replay checkpoint remains
before full historical certification/rollout, after the complete workflow exists.

## Technical findings / implementation checkpoints

Existing models already separate FinancialSale, FinancialReceipt and BankMovement
(the general actual-money ledger). Invoice links and assigned payment channel/studio
exist. No explicit collection allocation/reconciliation model exists yet; the
reconciled booleans must not substitute for one. FeePolicy and SettlementPolicy are
effective-dated configuration, not a completed reconciliation engine.

Reuse existing company/site/studio/account visibility and money/sensitive permissions.
A user who can see invoices does not necessarily have authority to see full bank
accounts; aggregate totals/drilldowns must enforce the intersection of visibility
and make partial scope clear. Never leak hidden studio/company values via totals,
counts, candidates or history.

Validate gross/payment cancellation semantics and effective receipt assignments
against existing posting/read APIs before implementing the aggregator. Test decimal
rounding, policy date boundaries, same-invoice split payments, repeated equal actual
receipts, missing classifications, unverified cash balances and amount conservation.
Use isolated test databases; do not insert synthetic money into the client's working
records. Preserve current pending bank overlap decisions for separate review.

## Definition of done for C-1

- Client-approved table basis is documented.
- Read-only endpoint/page show internally consistent per-day/method/studio totals
  with exact decimals and source drilldowns under existing permissions.
- Missing or ambiguous evidence cannot masquerade as a complete reconciled day.
- Tests prove no source/reconciliation state mutation and no cross-scope data leak.
- Client receives What I did / What you should test and a bounded list of remaining
  work. Code, rules and progress are documented for the next developer.
