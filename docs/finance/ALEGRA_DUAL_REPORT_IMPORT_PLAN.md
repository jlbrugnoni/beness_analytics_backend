# Alegra invoice and payment import plan

Date: 2026-10-25. Planning only; payment-report importer is not implemented.
Client accepted using both reports after historical inspection revealed payment
splits. This supersedes the earlier assumption that invoice-level payment methods
are sufficient. Spain remains Mindbody-based; this change initially concerns DR.

## Recommended operator sequence

1. Upload the original Alegra invoice/item report for the intended period.
2. Review invoice identity, amount, cancellation/status and studio assignments.
3. Upload the original Alegra payment/administration export, including payments
   collected in the intended period even when the associated invoice is older.
4. Review payment-to-invoice links, payment methods, splits and outstanding amounts.
5. Upload bank reports and reconcile settlements against linked payment allocations,
   allowing for terminal, payment channel, processing fees and settlement dates.

This is a convenient sequence, not a required storage order. Banks may continue
being uploaded daily independently of the sales reporting cadence. Never demand
that the client re-upload an existing bank report solely to establish a sales link.
Uploading two reports is not a single atomic file operation. Upload/preview,
financial posting and confirmed bank reconciliation are distinct operations.

## Either order must converge

| Arrival order | Expected behavior |
| --- | --- |
| Invoices first | Keep one sale per company/provider/full invoice code; payment breakdown remains incomplete, not invented from the sales method. Link valid payment evidence when it arrives. |
| Payments first | Retain payment source and stable payment record if identity is valid, pending invoice link. Do not fabricate a sale or a studio. Recheck pending links when invoice records become available through authorized posting. |
| Bank first | Keep existing bank transactions; settlement matching remains pending until linked payment evidence is available. No new bank movement is created by a payment export. |
| Repeated or overlapping files | Retain raw source history, reuse the same financial identities and preserve manual assignments. Do not create another sale/payment because the file name or row position changed. |
| One report corrected later | Keep prior evidence; propose changed amount/date/code/status for explicit review. File upload time alone does not determine which evidence is correct. Missing rows do not delete existing records. |

Automatic invoice/payment linkage is eligible only for exact full source invoice
identity in the same company/provider, after both financial records are available
and evidence has no identity/conflict issue. Matching suggestions from raw previews
do not post data. Missing code, ambiguous identity, cancellation, currency conflict,
changed evidence or excess allocation remains for review. Other valid records can
proceed. Customer-name/amount/date similarity alone never confirms a link.

## Record responsibilities and safeguards

- One invoice with its original items, date, total, status and studio evidence.
  Existing cost-center precedence, manual overrides and conflict warnings remain.
- Separate payment receipt with original source identity/date/amount/method and
  allocations to invoice(s). Confirm whether the native export represents one
  receipt across several rows/invoices before defining database uniqueness.
- Several receipts may pay one invoice; if supported by the raw source, one
  receipt may allocate across invoices. Sum allocations once per receipt and do
  not repeat an invoice total per item or payment. No imported totals overwrite
  original invoice facts merely to make a payment sum agree.
- Validate a stable payment ID in the native export. Do not use invoice code,
  payment amount/date/method, file hash or row number alone as receipt identity.
  If identity cannot be established, stage for review rather than collapse genuine
  identical payments. Cross-file deduplication must be independent of upload order.
- Payment allocations inherit resolved invoice studio for attribution; ambiguous
  or missing studio remains unresolved. Unmatched private payment evidence stays
  restricted to full-company finance scope until attribution is known.
- An invoice's default payment method is provisional evidence only when actual
  receipt breakdown is missing; never synthesize a full payment alongside imported
  receipts. Existing sale-channel data is preserved with provenance and must not
  silently override the imported receipt method or explicit manual corrections.
- Cobrada is status evidence, not a second receipt. A partially paid or Por cobrar
  invoice with receipts must be representable; the current sales reader/posting
  holds unrecognized/outstanding statuses for review and needs deliberate extension.
- Bank settlement estimates use actual allocated payment channels and dates when
  known, including channel-specific fees. Invoice date, receipt date and bank value/
  transaction date remain separate; use the approved date basis for each view.
- Sales and collection metrics remain distinct. Payments and bank deposits do not
  add revenue on top of invoices. Missing receipt evidence must be labeled as
  incomplete and excluded from claims of fully validated channel reconciliation.
  Outstanding/partial-payment management-result timing needs a targeted decision
  before implementing period reporting; do not infer a new revenue policy here.
- Preserve source version mismatches for review. Client attributes the observed
  September anomalies to differing report versions; that explanation is recorded,
  not permission to overwrite or automatically resolve the mismatched records.
- Cancellation/refund/replacement policies remain audited, without a double result
  deduction. No payment export triggers a refund bank debit automatically.
- Commit and linking require company-scoped concurrency controls, stale-plan checks
  and audit history. Undo cannot leave a confirmed allocation dangling: protect
  dependent records or require explicit reviewed reversal, keeping source evidence.

## Required discovery before coding

Inspect a native, unmodified Alegra payment report covering the September examples.
Confirm report type, columns, stable receipt ID, full invoice references, receipt
versus invoice dates, currency, refunds/voids, cash/card splits, multi-invoice
receipts and whether account fields reliably identify cash versus bank. The
prepared Alegra_adm sheet cannot alone establish that native layout contract.
Ask only questions unresolved by the source; do not assume payment Numero is a
globally unique receipt ID from workbook evidence alone. Compare report cutoffs
and explain coverage independently for invoice, receipt and bank periods.

## Development sequence and acceptance

Insert Phase 3.3.3 before historical financial posting (3.4.2):

1. Native payment-report discovery and fixtures; confirm unresolved business cases.
2. Immutable payment previews with totals, identity/coverage warnings and privacy.
3. Receipt/allocation model, reviewed commit, exact invoice linking, retry/overlap,
   manual assignment preservation, dependent undo and concurrency safeguards.
4. Extend invoice status/payment completeness handling without inventing receipts.
5. Show invoices, payment breakdown and unresolved cases; adapt historical migration
   and settlement reconciliation to the shared receipt/allocation model.

Acceptance must include invoice/payment/bank arrival permutations producing the
same final identities and totals; same-file and overlapping retries; staged payment
with no invoice; missing code; identical genuine payments; mixed card/cash and
transfer/cash; partial payments on different days/months; multi-invoice receipts if
present; cancellation/refund; source-version conflict; permission scopes; stale
plans/concurrent imports and undo with dependencies. Four September split-payment
examples in SEPTEMBER_ALEGRA_COMPARISON.md provide historical reference cases.
No implementation or passing-test claim is made for this planned behavior.


## Uploaded preview #3 inspection

2026-10-25: client identified existing preview #3, Ingresos_Egresos_DO_BI2.xlsx.
Verified same immutable SHA-256 as preview #2 and duplicate_of=2. No further upload
of this workbook is needed. Read-only inspection of saved values and formula text:

- Alegra_adm has 1,128 dated payment rows, Sep 1–Oct 22, 2026; 1,127 populated
  Numero values, all distinct within this sample. Row 183 lacks Numero. This
  supports a company/provider payment-number candidate, not proof of global
  uniqueness or native receipt identity across years/accounts/other exports.
- Every dated row has exactly one full B01/B02 invoice code in Asociaciones.
  All 1,127 populated NCF formula caches agree with that explicit source reference.
  NCF is a derived formula field (RIGHT of Asociaciones), not required linkage.
- Row 183 explicitly says Facturas: B0200004842 in Asociaciones despite blank NCF.
  Prior candidate-only conclusion based on blank cached NCF is superseded by this
  explicit reference. Preserve customer-label discrepancy and missing payment
  number as review evidence; do not invent a stable receipt ID or post it blindly.
- Metodo_pago is original-method evidence; Metodo holds enriched Cierre, Link,
  Recurrente, Transferencia or Efectivo assignments. Preserve both; explicit
  enriched/manual choices are not replaced by defaults from invoices.
- All rows have Tipo_nota Ingreso. Estado is blank throughout. Conciliada and
  Conciliado are separate populated source fields and are not proof of a new
  bank-to-sales reconciliation. No refund/void/multi-invoice receipt shape can be
  established from this sample.
- Enriched Metodo counts: Cierre 727, Link 134, Recurrente 165, Transferencia 69,
  Efectivo 33. Source account, date, amount, invoice references, payment number,
  original/enriched methods, manual studio and review flags are available to define
  a workbook payment-preview preset. Do not use customer ID column ID as receipt ID.

The workbook provides enough structure to design and build a bounded historical
Alegra_adm preview preset, with source identity warnings. Its existing migration
preview still only parses movement sheets into migration rows; other sheets are
retained in original bytes. No payment importer is implemented by this inspection.
A separate native standalone CSV importer must still validate an actual native
export before claiming support for it. This is not a reason to request the same
workbook again or block workbook-preset preview design.
