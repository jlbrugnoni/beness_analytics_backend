# Historical Alegra sheets and bank-status clarification

Delivered locally 2026-10-26 on feature/finance-phase-2 (backend and frontend).
Client accepted this delivery on 2026-10-26 ("i think all is correct"). No production
release or automatic financial posting. This acceptance covers the tested migration
workflow/UI; it does not certify the complete historical ledger or later report replay.

## Client report and findings

After importing workbook bank entries, the client reported empty debit method/terminal,
Unreconciled on all rows, reviewed debits/pending credits, and absent Alegra records.
These have distinct causes and should not be solved by fabricating missing data:

- Debitos has no payment-method or terminal columns. Those workbook columns belong
  to Ingresos. Hide these receipt fields/filter in the debit editor/table; retain
  existing stored values and API compatibility. The client was asked whether to keep
  manual expense assignments; no answer received at delivery, so this uses the
  recommended simpler UI pending their feedback.
- Debitos has a Conciliado checkbox, historically agreed to mean recognized/reviewed
  in the app when required classifications are complete. Ingresos has no corresponding
  checkbox. Complete data does not itself assert a human review. Do not auto-review
  all credits, undo the client's later edits, or fabricate invoice/bank matching.
- Reconciled is a separate ledger flag for established reconciliation. Importing a
  source or linking Alegra payments to invoices does not reconcile bank movements.
  Bank Records now prioritizes Reviewed / Needs review with a short explanation;
  unsupported reconciliation filters are removed from the bank work queue. Actual
  reconciled flags remain unchanged and remain visible if present.
- The prior bank bridge imported Debitos/Ingresos only. Alegra_adm already had a
  separate payment importer, but its entry point was secondary; Alegra items had no
  workbook adapter. A bank import must not silently claim it imported the other sheets.

## Delivered workflow and logic

The historical screen has Bank movements and Alegra invoices and payments tabs.
The Alegra tab reads both named sheets, showing independent row counts, totals and
issues, then prepares both previews. All dates are included; no pilot-month cutoff.
Preparation creates source previews only and is repeatable without creating another
pair for the same preview. Import invoices first through the existing sales panel,
then follow the explicit Review / import Alegra_adm payments link and confirmation.
Payment-first also remains supported: normal link refresh attaches payments when
invoices subsequently arrive. No payment is another invoice or another bank movement.

The invoice adapter uses the bounded non-evaluating XLSX reader and normal Alegra
CSV semantic parser/grouping rules. Numeric Excel dates, shared strings and saved
formula values are read without recalculation. Observed legacy header encoding
(FECHA DE EMISI”N, C”DIGO, M…TODO DE PAGO) is repaired for header matching only.
Original workbook bytes and cell evidence remain intact. Rows with cell/formula/cache
errors cannot silently become eligible paid invoices. Missing sheets/headers, limits,
ambiguous sheets/required headers and invalid source values fail closed.

Invoices group by code, retain item occurrences, and count the invoice total once.
Cost center, price list, original method and client facts enter the existing mapping
and discrepancy rules. Alegra_adm remains the payment source, including fractional
payments and manually corrected methods/studios. Egresos remain excluded by existing
payment posting. Missing payment numbers remain pending rather than invented.

SalesImportBatch.migration_batch (migration0016) records workbook lineage. Derived
invoice previews retain the XLSX original with correct download MIME; item rows retain
source row/sheet/cells as evidence. No duplicate sales ledger or reconciliation model.
The sales fact comparison now normalizes only numerical representations in item
quantity/price/amount and explicitly numeric item-evidence fields. This allows XLSX
1/100 and CSV 1.00/100.00 to link as the same invoice, while real numeric changes,
client/identity changes and text evidence remain anomalies. Bank matching is unchanged.
Sales plan version2 invalidates previously generated plans after this semantic change.

## Current local data and safeguards

The client copied workbook preview6 to preview8/company1 and posted322 bank movements
before this work. At investigation:151 debits/171 credits;144 debit review flags true,
7 false;170 credit flags false and1 true. All322 reconciled flags false. No assignments
or flags were changed by this delivery; browser opened/closed an editor without saving.

Preview8 contains793 invoice-item rows grouped into744 invoices and746 payment rows,
covering August1–September1. Both source totals are4,518,564.40DOP. Two payment groups
are split, and one payment lacks its number. Browser Prepare created invoice preview9
and payment preview9 under company1; the invoice posting plan has744 new invoices.
These are reviewable previews only: FinancialSale and FinancialReceipt counts remain0;
bank count remains322. The old company5 payment preview is not moved or posted.
No reset, real sales/receipt posting, automatic flag changes or production DB changes.

Before migration0016, a full verified SQLite/source-blob backup was saved outside Git
at .local-backups/before-alegra-workbook-20261026T133428/database.sqlite3 with private
permissions. Migration applied only isolated QA/tests. Backend8027/frontend3037 restored.

## Validation and client tests

Full finance suite passed276 tests on a fresh isolated PostgreSQL test database.
Focused workbook tests cover numeric dates/legacy headers, item grouping, formula
errors, named-sheet validation, explicit/idempotent preparation, permissions, both
posting orders, split receipts, no bank writes, repeated commits, native report overlap
and genuine price changes. Frontend changed-file lint and production build passed;
migration drift and whitespace checks passed. Browser verified recognized counts,
prepared invoice plan/payment step, debit review status and editor without receipt
fields. No synthetic fixtures were added to the client dataset this turn.

Client acceptance steps:
1. Refresh Records; debit columns/editor should be expense-focused and the primary
   bank status should be Reviewed / Needs review. Existing flags should be unchanged.
2. Initial setup → QA financial company → workbook8 → Alegra invoices and payments.
   Both previews are already prepared; no need to upload the workbook or bank rows again.
3. Review and confirm Import sales for744 invoices. Check invoice amounts/studios/items.
4. Use Review / import Alegra_adm payments, review and confirm. Expect the payment
   without a number to remain pending; verify split payments and invoice links.
5. Compare later routine reports in the same company. Matching reports link; genuine
   source changes remain reviewable. Reviewed is still separate from reconciliation.

Historical cash/manual ledger, full migration certification, bank reconciliation and
monthly management results remain unfinished. Do not describe this as full Phase4/5
completion or clear outstanding review items merely because the totals match.
