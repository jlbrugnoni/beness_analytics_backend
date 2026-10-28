# September Alegra acceptance rehearsal and legacy text recognition

2026-10-28. Development branch `feature/finance-phase-2` in both repositories.
Client acceptance of the record-editor close fix precedes this increment. No merge,
push, deployment, working-data reset or permission changes are included.

## Sources and findings

Working sales import10: `Alegra - Facturas - Beness Pilates Studio S.R.L. --10 copy.csv`.
Working payment import10: `Alegra - Reporte de transacciones - Beness Pilates Studio S.R.L. - copy.xlsx`.
Historical invoices/payments came from workbook8 through sales9/payment9, August1–September1.

The current native reports agree:611 invoices,654 item rows,615 incoming payments,
four split-payment invoices, and3,555,130.80DOP gross in each report. The transaction
report also contains67 Egreso rows. They are excluded from incoming-payment posting;
the existing API internally labels them invalid, while the daily UI labels them excluded.
There are no Anulada invoices in this actual sample; cancellation behavior remains
covered by synthetic regression tests rather than a claimed real cancellation case.

The invoice import had470 creations,3 links and138 pending source anomalies, all on
September1. Every pending row has the same date and invoice total as its historical
counterpart. All138 are explained completely by the observed legacy Mac Roman/
Windows-1252 text mistake (for example `crÈdito`/`crédito`, `dÌas`/`días`), after the
existing numeric-presentation comparison. Six September payment-to-invoice customer
conflicts have that same cause. No other fact changes were found among those138.

## Comparison behavior (D-089 implementation)

Recognize the observed encoding relationship only when comparing a historical-workbook
invoice with a native-report invoice. Build a temporary comparison copy; change a text
value only if the exact reversible codec conversion occurs in the counterpart's text.
The complete invoice header/item fact signature must then agree. No fuzzy names,
approximate amounts, dropped items or automatic customer/source replacements.

Native-to-native differences, real customer/service/amount changes, cancellation and
stale-paid states retain their existing review rules. Raw files, cached values, current
invoice source/items, and manual studio/method assignments stay untouched.

For exact payment invoice links, the same legacy exception is allowed only with
historical provenance and an invoice code involved in the current import/recovery.
Existing exact code/company/provider/status/allocation checks remain. Genuine customer
conflicts stay unresolved. Unrelated historical customer conflicts are not revisited
by this recovery. Links may change, never the payment amounts or saved assignments.

Sales interpretation token advances tov3 and payment interpretation tov2. No schema
migration. Existing previews require refresh under the new comparison version.

## Recovering already-posted invoice import10

Upload reports → Alegra invoices/items → Upload history → Open native report →
**Link recognized invoices (138)** → confirmation. It links only pending decisions
whose current complete facts match; no new sales or source corrections are created.

GET `sales-imports/{id}/processing/` adds pending_count/ready_count.
POST `sales-imports/{id}/apply-pending/` requires a fresh expected_plan and existing
import/edit/full-company sensitive-source access. It holds the company lock and applies
audited links atomically, then refreshes only relevant legacy payment links. Previous
decisions remain in force. A stale retry fails409; a fresh retry is a no-op. Genuine
anomalies/cancellations are never bulk accepted. No extra user grant is introduced.

The working report remains pending138 for client testing; its six affected payments
remain customer-conflict pending until an authorized import/recovery refreshes them.
The browser confirmation was inspected and cancelled, not submitted.

## Isolated actual-report rehearsal

Consistent SQLite copy, private temporary folder `finance-alegra-rehearsal-5ekxzbtj`;
database and `rehearsal.json` are disposable diagnostics, not a production backup.

1. Recovering the current invoice import linked138 decisions and resolved exactly6
   September payment customer links. Invoice rows/items/amounts/studios/methods,
   receipt sources/amounts/manual assignments, bank movements/classifications and
   saved check/event records were preserved. Unrelated August links stayed unchanged.
2. Repeated source uploads recognized611 invoices and615 incoming payments, with67
   excluded outgoing rows; no extra sales or payments were created.
3. In a separate empty disposable company, upload invoices then transactions.
4. In another empty disposable company, upload transactions then invoices.

Both orders produce611 invoices,654 items,615 payments,4 split invoices and the same
3,555,130.80DOP invoice/payment totals. Every payment links to the exact invoice;
per-invoice payment sums equal the invoice total. Final source facts, studios/methods
and links agree by invoice code/payment number across orders. Repeating both reports
in each company creates no additional invoices or payments.

332 PostgreSQL finance tests passed, including10 new legacy-text/recovery regressions.
Changed-file frontend lint, production build and migration drift checks passed.
The real sample validates split payments and repeated imports; regression cases also
protect real customer/fact changes, cancellations, native-source differences, scope
revocation, stale/repeat recovery and unrelated historical links.

## Client acceptance and next operational work

1. Refresh and open native invoice import10. Confirm138 recognized invoices, then
   use Link recognized invoices. Expect pending0,141 total links and470 creations;
   invoice counts/amounts/classifications must not change.
2. Inspect an affected September invoice such as B0200004760: its existing payment
   should now be linked. A known split invoice such as B0200005029 retains both payments.
3. Re-upload/preview the native invoice/payment reports if desired. Expect recognized
   rows and no extra financial records; outgoing transactions remain excluded.

This completes technical upload-order/overlap rehearsal, not full monthly bank/sales
reconciliation. Finish legitimate classifications/operation dates, cash coverage,
remaining bank20 decisions and September closure comparison with the client's
complete document. Partner-profile acceptance and production cutover remain in
DR_OPERATIONAL_RELEASE.md. Spain/analytics remain later releases.
