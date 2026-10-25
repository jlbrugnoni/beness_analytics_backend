# Phase 2.4 fees, settlement timing and company tax profiles

Date: 2026-10-24. Phase 2.3 accepted (D-039). Q-010 sent; answers pending.
This is discovery and proposed implementation scope, not delivered functionality.

## Confirmed inputs

- DR Cierre and recurring: 3.5%; Link: 5%. Historical baseline throughout
  available coverage, without an invented contract start date (D-030).
- AZUL deposits arrive net. Estimate withholding once; later actual evidence
  replaces/adjusts estimates without duplicate expenses (D-009–011).
- Distinct transfer/bank charges remain separate expenses. Unidentified AZUL
  debits remain review items. Do not derive actual fees solely from a mismatch.
- Caixa charges and separately reimburses terminal fees during its first-year
  offer. Preserve both movements; reimbursement is an expense offset, not sales.
  Exact amounts, dates and gross/net deposit behavior remain unconfirmed.
- Company sales tax defaults: Spain 21% included; DR activity no sales tax,
  as supplied by the client. V1 result and allocation weights remain inclusive.
  Explicit source tax takes priority; no expense IVA inferred from bank amounts.
- Default review tolerance is 0.01 DOP/EUR, configurable; no automatic write-off.

## Q-010: questions sent

1. In Spain, does Caixa deposit the full card-sales amount and charge terminal fees separately, or deduct anything from each deposit?
2. What is Caixa's fee arrangement (monthly amount, percentage, or both), and when does the first-year reimbursement offer start/end? Unknown settings can remain pending rather than zero.
3. For DR Cierre, Recurrentes and Link, do deposits normally arrive within the previously mentioned 24–48 hours? Do weekends delay them? Timing guides suggestions; operation dates remain editable.

## Proposed development scope

- Editable company/channel fee policies with historical baseline or dated
  applicability. Preserve revisions/audit and reject conflicting effective rules.
  Missing rules produce unknown/review, never a fabricated zero charge.
- Settlement timing configuration as suggestions, separate from bank and
  operation dates. No silent date reassignment. Do not pretend business-day
  estimates include a holiday calendar that is not implemented.
- Company sales tax profiles with dated defaults and explicit inclusive/no-tax
  treatment. Changes must not silently restate existing financial records.
- Reuse settings capability, full-site scope, stale-save protection and EN/ES UI.
- Configuration and interpretation tests only at this checkpoint. Bank import,
  fee estimates on financial records, reimbursement matching, actual-fee
  adjustment periods and monthly calculations belong to later processing phases.
- Generic configuration work can support unknown Spain terms. Answers govern
  initial values; unanswered questions do not authorize guessed defaults.

No new code, migrations, financial entries or reports were created during this
checkpoint. Keep both repositories on feature/finance-phase-2.
