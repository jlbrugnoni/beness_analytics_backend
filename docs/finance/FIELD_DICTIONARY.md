# Finance field dictionary

Status: Phase 0 accepted, 2026-10-24. Names describe the target domain;
exact Django field/API names are finalized during implementation. Phase 1 delivery
and Phase 2.1–2.3 deliveries list the implemented company/account/terminal/category/source-mapping/access subset; other records remain planned.

## Ownership and configuration

| Record | Fields and meaning |
| --- | --- |
| Company | Name, country, default currency, linked operational site context. DR Beness Pilates Studio S.R.L.; Spain Bewellness Group SL. A site is not automatically a company. |
| Account | Editable label, company, bank/cash type, currency, provider, participating studios, active status. DR-first proposed label Banco Popular - Cuenta operativa (DOP). Optional reference opening balance/date (start of day) and statement-import expectation; unknown balance differs from zero. No expected-balance calculation yet. External account identifier optional; credentials are not collected. |
| Terminal | Identifier as text, provider, account/company, existing studio, payment channel, active state and revision. Effective dates remain future configuration work. Estepona identifier 369092994. |
| Category/subcategory | Company-owned editable names, immutable parent, stable catalog code, operating/extraordinary/review defaults, shared/direct default, own/effective sensitive and active flags, record/parent revisions. Used categories are archived, not destructively deleted. Parent sensitivity applies to children. |
| SourceMapping (implemented) | Company/source field/reported value identity, normalized exact key, map/review/neutral action, studio/channel target, review flag, active, revision. No regex/fuzzy matching. Manual choices take priority while raw values/rule evidence remain. |
| Fee/date rule (future) | Fee rate/amount, effective dates, settlement/date interpretation and reviewed provenance. Source mapping does not calculate fees. |
| Tax profile | Company default sales treatment/rate, prices-inclusive flag, effective dates. V1 uses inclusive results; expense tax is not guessed. |
| Source policy | Company/period, one authoritative source. V1 DR Alegra; Spain existing Mindbody Sales. No Spain Alegra cutover is assumed. |

## Import provenance

| Field | Meaning |
| --- | --- |
| Creation origin | Manual, routine source import, historical migration, or explicitly source-linked projection. Manual edits do not change origin. |
| Source batch/name | Original filename, import ID, source type, actor/time, account/company context. Show the source name subject to permissions. |
| Raw row / source reference | Original payload, row location, optional source identifiers, original amount/dates, first/latest seen imports. Not a manual classification. |
| Identity / version | Stable system identity independent of mutable classifications; source fingerprint/context/occurrence and history support overlap review. File hash alone is insufficient. |
| Coverage | Actual date range and source availability. Missing income for an expense period means incomplete coverage, not zero sales. |

DR historical data starts January 2026. Spain expenses start mid-2025 (exact month
not given) and income starts February 2026. Imported files establish actual bounds.

## Movement and classification

| Field | Meaning |
| --- | --- |
| Bank/payment date | Date money moved, preserved from source; manual entries identify their entered date. |
| Direction, amount, currency | Inflow/outflow and decimal value with explicit currency; no combined EUR/DOP sum. Preserve raw signs. |
| Balance | Source-reported bank balance where provided; manual entries do not create a verified balance. |
| Original description/reference/serial | Immutable bank evidence; optional and not globally unique. Sensitive details require protection. |
| Business description | Entered explanation, independently editable with actor/time history. |
| Operation date | Assigned sales day underlying a receipt. Extract Caixa DDMM using the bank date for year context; otherwise manual/rule assignment. |
| Expense period | Month cost belongs to, independently of payment date; used for expense reporting and shared-cost allocation. |
| Studio/channel/terminal | Mapped assignments linked to existing studio/configuration; unknown values enter review. |
| Movement kind | Sales receipt, expense, internal transfer, fee/reimbursement, refund, or extraordinary movement. Not equivalent to debit/credit. |
| Category and treatment | Expense category/subcategory plus operating/extraordinary/shared classification. Sensitivity is independent of financial treatment. |
| Statuses | Review, classification completeness, and reconciliation are separate. Legacy reviewed flag does not fabricate a settlement match. |

## Sales, refunds, fees, and allocations

| Record | Fields and meaning |
| --- | --- |
| Invoice/sale | Company/source/code, sale and assigned payment date, studio, source method and mapped channel, original tax-inclusive total, source status, optional client identity. |
| Item | Parent sale, occurrence, service/description, quantity, price, discount, explicit tax if supplied, line total. Identical legitimate items remain separate. |
| Refund adjustment | Original sale link, original result period, actual refund date/channel, amount, source evidence, cancellation linkage. Source reversal must not be applied twice. |
| Settlement | Group of receipts and sales with allocated amounts, expected gross, estimated fee, actual net, remaining amount, exact difference, reviewed resolution. |
| Fee | Withheld versus separately charged, estimated versus actual, source/rule evidence and applicable period; actual replaces/adjusts estimate, not double expense. |
| Fee reimbursement | Separate credit linked to fee debit with provider eligibility context. Preserve both source legs; no customer sales increase. |
| Internal movement | Source/destination own-company accounts, imported leg references, amount/currency, counterpart status. Do not invent an unimported bank leg. |
| Administration allocation | Source company cost, expense month, company/studio gross-sales basis including IVA before fees, weights, amounts, remainder, manual override, source version. Zero-income month stays pending. |
| Sensitive access | Extra capability for individual detail; authorized aggregates still include the expense. Redaction must not remove costs from result calculations. |

## Result definitions

- Gross sales: authoritative tax-inclusive sales before processing fees, adjusted
  for refunds in the original sale period.
- Operating result: gross sales less applicable processing fees and operating
  expenses, with direct/shared costs counted once.
- Final management result: operating result + extraordinary inflows -
  extraordinary outflows. Financing can affect this custom final figure.
- Employment taxes/contributions: operating; client-described revenue-related
  taxes: non-operating. Map actual categories during setup; unknowns enter review.
- Studio results include allocated administration; company results include the
  company expense once, not the parent plus its allocation children.
- Default rounding-review threshold: 0.01 DOP/EUR, configurable, no automatic
  match/write-off. Do not change source amounts to force a match.
- Month closing and net-of-tax result: deferred; retain audit/period structure.

These are custom management measures. A formal EBITDA measure requires a separate
agreed definition; it is not an alternative label for the final financing-inclusive
figure.
