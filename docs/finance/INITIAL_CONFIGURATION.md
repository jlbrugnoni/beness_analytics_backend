# Confirmed initial financial configuration

Date: 2026-10-24. Client-provided values, not independently verified bank balances
or contractual fee terms. Production configuration has not been created.

## Dominican Republic accounts

Company: Beness Pilates Studio S.R.L., currency DOP.

- Banco Popular - Cuenta operativa (DOP): statements expected; opening balance
  unknown until provided or established from source evidence.
- Banco Popular - Cuenta de ahorro (DOP): no statements expected. Client states
  the year began with zero balance; record 0.00 DOP at the start of 2026-01-01,
  before that day's movements. Historical migration contains internal transfers
  to savings. Savings is retained even without recurring statements.

Future expected balance = reference opening balance + known internal receipts and
other recorded inflows - recorded outflows, since the reference date. Include an
own-company transfer once even when both imported legs later become available.
An unimported destination leg is an expected receipt, not fabricated bank
confirmation. Missing savings statements must not automatically create a missing
routine-import alert when statement_imports_expected=False. Unknown reference
balances stay unknown, not zero. Reconciliation and expected-balance calculations
are later phases; Phase 2.1 stores reference values and the statement expectation.

## Dominican Republic terminals

Initial settlement account: the Dominican Banco Popular operating account.
Terminal identifiers are strings. This explicit table supersedes illustrative
terminal/location examples from initial discussion.

| Identifier | Payment type | Existing studio |
| --- | --- | --- |
| 39618800002 | Cierre / card_terminal | Beness Pilates - Bella Vista |
| 39618800004 | Recurrentes / recurring | Beness Pilates - Bella Vista |
| 39618840003 | Link / payment_link | Beness Pilates - Bella Vista |
| 39618800001 | Cierre / card_terminal | Beness Pilates - Piantini |
| 39618800003 | Recurrentes / recurring | Beness Pilates - Piantini |
| 39618840001 | Link / payment_link | Beness Pilates - Piantini |
| 39618800006 | Cierre / card_terminal | Beness Pilates - Arroyo Hondo |
| 39618840004 | Link / payment_link | Beness Pilates - Arroyo Hondo |

No recurring terminal was supplied for Arroyo Hondo; do not invent one.
Spain's previously confirmed 369092994 -> Estepona remains accepted (D-004).
Do not invent Spain's channel, commission, or settlement-account setup from DR.

## Dominican Republic fees

| Payment type | Estimated withholding percentage |
| --- | --- |
| Cierre (credit and debit cards) | 3.5% |
| Recurrentes | 3.5% |
| Link | 5% |

Client reports these have applied "since forever". Treat as defaults applicable
throughout available historical coverage; no rate change/start date was supplied.
Future dated fee configuration must permit this historical baseline without
inventing an actual contract date. No fixed charge was confirmed. Unknown methods
remain for review rather than being assigned one of these rates or zero.

These rates are documented inputs for Phase 2.4, not executable rules in Phase
2.1. Fee calculation and comparison with net deposits arrive in later processing
phases. Preserve P-002's single deduction and actual-adjustment treatment.

## Category catalog (D-032–035)

The common starting catalog contains 10 categories and 45 subcategories. The
explicit workbook table is preserved in PHASE_2_2_DISCOVERY.md, plus accepted
Otros / Extraordinarios. Initialize separately per company; common catalog codes
remain stable across initial copies. Existing live edits are never overwritten.

Personal is sensitive, as are the two Administracion payroll/social-security
children. Ordinary costs default operating; revenue-related Impuestos and
Extraordinarios default extraordinary; Equipamiento, Intereses and Devoluciones
require review. Administracion defaults shared administration; explicit historical
studio assignments must still be preserved during later migration.

These are editable classification defaults, not automatically applied financial
entries. The invalid historical 1 / 1 pair is not a catalog entry.
