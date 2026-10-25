# September 2026 Alegra / Alegra_adm comparison

Date: 2026-10-25. Read-only inspection of client-uploaded migration preview #2,
Ingresos_Egresos_DO_BI2.xlsx in the isolated local app. Neither workbook nor
financial records modified. Values are saved formula caches, not recalculated.
Source: /finance/migration-imports, preview #2; exact worksheet rows below.

## Count explanation

Alegra: 654 item rows grouped by full CÓDIGO = 611 September invoices.
Alegra_adm: 615 September payment entries; 614 populated distinct Numero values,
one blank Numero. Numero identifies payment entries, not invoice codes. Match
Alegra CÓDIGO to Alegra_adm NCF instead. There are 610 populated distinct NCFs
and one entry with blank NCF. Four NCFs each have two payment entries.

Thus 610 coded invoices + four additional payment entries + one uncoded entry
= 615 administration rows. Alegra has the 610 common codes plus B0200004842.
The prior shorthand “615 invoice numbers” was inaccurate; this corrects it.

## Four invoices with split payment entries

All amounts DOP. These are not duplicate sales; each payment pair sums to one
Alegra invoice. Do not delete an extra payment or create another invoice.

| Invoice | Date | Studio | Alegra row / total | Alegra_adm rows / payment entries |
| --- | --- | --- | --- | --- |
| B0200005029 | 2026-09-09 | Bella Vista | 374 / 3,600 | 337: Numero 6107, Cierre 1,200; 338: Numero 6106, Efectivo 2,400 |
| B0200005090 | 2026-09-14 | Piantini | 440 / 3,600 | 405: Numero 6173, Cierre 2,600; 406: Numero 6172, Efectivo 1,000 |
| B0200005226 | 2026-09-29 | Piantini | 599 / 3,600 | 540: Numero 6313, Cierre 600; 541: Numero 6312, Efectivo 3,000 |
| B0200005267 | 2026-09-30 | Bella Vista | 644 / 5,440 | 581: Numero 6356, Transferencia 4,000; 582: Numero 6355, Efectivo 1,440 |

These historical mixed-payment records conflict with the earlier discovery
assumption of no mixed methods. Keep evidence; revisit payment allocations before
historical reconciliation/posting. Do not silently replace manual splits with a
single payment method from the original sales report. No implementation scope
change or confirmation of current practice is inferred from this inspection.

## Uncoded entry and candidate invoice

- Alegra_adm row 183: date 2026-09-02, 10,400 DOP, Link, Arroyo Hondo;
  both Numero and NCF blank.
- Alegra B0200004842, rows 164–165: date 2026-09-02, invoice total 10,400,
  Arroyo Hondo, Cobrada; two items 6,800 and 3,600. This code is absent from
  administration NCF values.
- Date, total and studio agree, but customer names differ and payment method
  differs (source credit-card default versus manual Link). This is a candidate
  for client investigation only, not a verified association. Never auto-link it.

## Other differences among common invoice codes

| Invoice | Studio | Alegra | Alegra_adm | Admin minus invoice |
| --- | --- | --- | --- | --- |
| B0200005012 | Piantini | Row 353, Sep 9, Cobrada, 6,800 | Row 358, Numero 6086, Sep 9, Cierre, 9,600 | +2,800 |
| B0200005135 | Bella Vista | Row 493, Sep 19, Por cobrar, 5,440 | Row 525, Numero 6272, Sep 28, Link, 3,600 | -1,840 |

Customer text agrees for both common-code anomalies. Amount/date differences
must be checked against actual invoice and payment history. Por cobrar versus an
administration payment record is additional review evidence, not proof of error.
All other common codes agree on date and total once split payments are summed.

Raw invoice-total sum counted once per invoice: 3,554,170.80 DOP (includes Por cobrar).
Administration payment-row sum: 3,555,130.80 DOP. Difference +960.00, numerically
explained by +2,800 -1,840 when the uncoded entry and candidate invoice are compared
at their equal total. That numerical equality does not verify their identity or
prove paid sales, profit, bank reconciliation or full source completeness.

## Source choice and next review

Client explicitly selected original item-level Alegra as sales source of truth.
Generate invoice summaries from that report. Preserve administration manual
corrections and payment allocations as separate evidence, not additional sales.
Client should search the six listed invoice codes and the uncoded row 183.
No deletions, edits, linking, migration posting or deployment performed.
