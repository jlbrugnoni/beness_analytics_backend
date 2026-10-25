# Phase 2.3 source/payment/studio mappings discovery

Date: 2026-10-24. Phase 2.2 accepted (D-036). Phase 2.3 questions answered (Q-009/D-037–038); implementation delivered for review.
This document preserves discovery. See PHASE_2_3_DELIVERY.md for implemented models, preview and UI.

## Source evidence and existing integration

Read-only inspection of the supplied item-level Alegra CSV found its header on
row 2 (after the export's separator hint). Mapping-relevant columns are CENTRO
DE COSTO, MÉTODO DE PAGO and LISTAS DE PRECIOS. Do not confuse TIPO DE PAGO
(Contado) or PLAZO DE PAGO (De contado) with the payment method/channel.

- Cost-center labels: Bella Vista, Arroyo Hondo, Piantini.
- Price-list labels: Bella Vista, Arroyo Hondo, Piantini, General.
- Payment-method labels in this sample: Tarjeta crédito, Efectivo, Tarjeta débito.
- Transferencia exists in the earlier workbook's payment-method setup; it is not
  a payment-method label observed in this particular Alegra sample.

The source file was not modified or copied into Git. Only non-personal mapping
labels are recorded here; no clients, invoices, amounts or raw rows are included.

Existing core_data.PaymentMethod is site-scoped. Existing SaleLine already has
site, studio, payment_method and original raw-row/import references. Finance must
not rename those operational records, rewrite their imported classifications,
or introduce another routine Spain sales upload. The later Spain adapter reads
existing sales while preserving source lineage (BR-008).

## Already accepted behavior — do not reopen

- Use Centro de costo as primary Alegra studio evidence. Flag a contradictory
  studio-specific price list. General is neutral. Missing/unrecognized cost
  center is a review issue; do not silently substitute the price list (BR-006).
- Initial DR studios are the existing Beness Pilates - Bella Vista, Piantini,
  and Arroyo Hondo. Terminal mappings and fees are already recorded in
  INITIAL_CONFIGURATION.md; do not infer a studio from payment method.
- Preserve original source payment labels separately from financial channels
  (Cierre/card terminal, recurring, link, transfer, cash, other) (BR-007).
- Mapping configuration is editable and audited. Manual decisions survive
  later imports/rule changes. Unknown/ambiguous input stays reviewable instead
  of blocking independent valid rows or inventing a zero fee.
- DR source is Alegra; Spain uses existing Mindbody Sales for now. Future Alegra
  Spain cutover is deferred (D-020). Dates, fees and taxes belong to Phase 2.4
  or later processing; this subphase does not compute settlements/results.
- Read/write scopes and financial settings capability remain authoritative.
  Mapping metadata must not expose full bank accounts through this surface.

## Q-009: client questions sent

1. Can current Alegra Tarjeta crédito/Tarjeta débito include Link or Recurrentes,
   as well as Cierre? If yes, recommend keeping their financial channel pending
   review rather than assuming Cierre. The workbook's generic card-to-Cierre
   mapping is evidence of its setup, not proof every historical invoice is Cierre.
2. Are Alegra Efectivo/Transferencia labels reliable enough for direct mapping,
   or should those also require review? Clarify trust separately from naming.
3. What exact Spain Mindbody payment-method names correspond to card terminal,
   recurring, link, transfer and cash? If unavailable now, leave Spain aliases
   unconfigured and support in-app maintenance; this does not block the generic
   configuration editor or DR mappings.

Answers received 2026-10-24:
1. Normally Tarjeta débito = Link, Tarjeta crédito = Cierre. Recurring payments
   are also recorded as Tarjeta crédito and must be distinguished manually.
   Use the Cierre suggestion plus a review flag, rather than the originally
   proposed fully unassigned generic-card channel (D-037).
2. Efectivo = cash and Transferencia = transfer, as confirmed in answer 1.
3. Spain currently has no recurring or transfer payments; clients normally use
   card in the studio and cash. Exact method labels were not supplied (D-038).
   Leave those aliases unconfigured instead of assuming English/Spanish labels.
No additional terminal/fee/category questions are needed at this checkpoint.

## Planned implementation after answers

- Editable source-specific exact label mappings per company, with normalized
  uniqueness and explicit studio/channel/neutral/review intent as appropriate.
  Match source fields separately; a price list is not a cost center.
- Retain original labels and rule identity/revision in the future resolution
  contract. Avoid fuzzy/pattern matching as an automatic initial default.
- Expose explicit pending/ambiguous outcomes and studio mismatch warnings;
  never claim a mapping preview imports or reconciles transactions.
- Reuse existing studios and access scope. Protect cross-company/studio targets,
  audit writes, reject stale saves, and deactivate rather than hard-delete.
- Add EN/ES configuration UI and focused tests for normalization, invalid targets,
  ambiguous card labels, neutral General, manual precedence and source mismatch.
- Remain on feature/finance-phase-2 in both repositories. Finish with documented
  checks and client review before Phase 2.4.

Detailed model/API choices are developer responsibilities. The questions above
concern source reliability and business classification, not technical approval.
