# Supervised January–August invoice/payment comparison

Read-only snapshot2026-10-28. Owner reports waiting invoices and customer conflicts
after importing the supervised Ingresos_Egresos_DO_BI.xlsx. Current source lineage is
migration9, invoice batch11 and payment batch11, company1. Analysis uses exact invoice
number/provider/company, sums split payments, retains raw names/dates/statuses and
never treats worksheet row positions as matching identities.

## Results

4,997 source invoices,4,881 posted invoices and4,984 posted payment receipts.
4,849 receipts linked;135 flagged:18 customer_conflict,116 invoice_missing and1
invoice_cancelled. No working data, link or financial fact was changed by this audit.
There are also21 rejected payment source rows, distinct from the135 posted warnings.

### Customer warnings

-12 exact invoice-number/amount/date matches where invoice says Consumidor final and
 payment adds a name after a slash.
-1 exact number/amount/date match with an abbreviated versus full surname.
-4 different named customers with equal invoice/payment totals. One payment is two
 days after invoice date. These require owner confirmation of payer/customer policy.
-1 name conflict also has an amount difference: B0200002104, invoice3,060.00,
 payment3,600.00, datesApr20/Apr21. Do not approve by name normalization.

None of these18 are solely the already-handled reversible legacy encoding mistake.
Preserve payer and invoice customer separately. No fuzzy matching or replacement of
customer facts was performed. A business question about payer-versus-invoice names
was asked and remains pending at this checkpoint.

### Waiting invoices

All116 payment references occur in the Alegra invoice source. The UI's current
invoice_missing label means no posted eligible FinancialSale, not necessarily that
the invoice number is absent from the workbook:

-114 receipts refer to114 source invoices with empty item and invoice totals. Source
 datesFeb6–12;120 item rows, physical Alegra rows909–1028, including B0200000790 and
 B0200000875. Quantity/unit-price/discount arithmetic equals the associated receipt
 sums for all114 invoices,552,680.00DOP. The original total cells are genuinely absent,
 not an encoding error or number-format parse failure. Arithmetic is diagnostic,
 not permission to replace missing final invoice facts with payment amounts.
-2 receipts refer to B0200001144, whose source status is Por cobrar and invoice total
 is1,200.00 while two receipts total6,800.00. This is a status/amount conflict.
-There is a second source Por cobrar invoice B0200003558,3,600.00, without a posted
 receipt. It accounts for the other rejected source invoice but not the116 payments.

### Other amount and payment coverage cases

| Invoice | Source total DOP | Posted payments DOP | Observation |
| --- | ---: | ---: | --- |
| B0200001491 | 2,380.80 | 2,380.00 |0.80 short; retain actual amounts |
| B0200002104 | 3,060.00 | 3,600.00 |540.00 over and names differ |
| B0200003369 | 3,600.00 | 1,440.00 |Possible partial/missing later payment;2,160.00 gap |
| B0200001144 | 1,200.00 | 6,800.00 |Por cobrar plus5,600.00 over |
| B0200002751 | 2,500.00 | 6,800.00 |Anulada; cancellation/payment/reference need review |

21 Cobrada source invoices have no posted payment; the additional Por cobrar invoice
also has none. Check rejected raw payments before assuming absent receipts. Payment
batch11 has21 invalid rows:16 missing payment numbers,4 repeated-number rows and1
unrecognized status MEDIAS. One repeated-number row also has an invalid amount.
Examples: Alegra_adm rows43/44 both use payment60 for different invoices; rows1242/
1313 both use1309, with the first lacking an amount. These are not safe duplicates
and must not be merged or given invented identifiers silently.

Invoice assignment warnings are a separate issue: many older rows have no cost center
or payment method, and some method text has legacy encoding. A recognized price-list
studio or supervised payment studio may be useful corroboration, but the current
rules do not infer missing invoice studio from it. Any fallback/backfill policy needs
explicit scope and conflict handling; do not hide these warnings while changing links.

## Recommended consolidation design (not implemented/applied)

1. Keep exact invoice number within company/provider as the link candidate, then
   show invoice/payment sums, status, dates and both original names together.
2. Recognize approved generic-consumer-name extensions and narrow full/abbreviated
   name equivalents only with exact identity, valid status and allocation checks.
3. Provide an explicit audited payer-differs approval for genuine different names,
   after the owner confirms this is valid business behavior. Preserve both names;
   never rewrite the imported client to force agreement.
4. Clearly distinguish invoice absent, invoice rejected for missing totals, rejected
   payment identifiers, status conflict and amount difference. One generic Waiting
   for invoice status hides the remedy. Group multiple payments under their invoice.
5. Repair missing invoice totals and rejected payment identities through a corrected
   source document or fresh Alegra reports. If owner approves calculated historical
   totals, design that as a separate evidence-backed migration repair rather than
   silently substituting collections. Never auto-create invoices from payment totals.

## Review deliverable and verification

Prepared Historical_invoice_payment_review.xlsx under outputs/
01a0f28b-e492-78b0-b518-6789ffd6048f/, with five filtered sheets:18 name conflicts,
27 other invoice amount/status/coverage cases,114 missing totals,21 rejected payment
rows and120 supporting item rows. Source Excel row references included. Issue sheets
overlap by invoice and must not be summed as a unique invoice count. Dates/numbers
are typed, money has grouping and two decimals. Formula checks confirm all114
arithmetic subtotals equal receipts; changing an item price changes the dependent
comparison and restoring it restores zero difference. Formula-error scan empty;
all five views rendered and visually inspected. No application code change or new
backend regression run required for this read-only analysis.

Private snapshot/audit and build inputs retained in
.local-backups/supervised-baseline-link-audit-20261028/ with private permissions.
Do not commit the snapshot, customer detail or exported workbook to the backend.
