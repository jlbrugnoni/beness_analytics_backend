# Spain historical migration delivery

2026-11-16: implemented locally; owner acceptance pending. Branch in both repositories
is feature/finance-spain-v2. No commits, pushes or production changes.

## Owner decisions

Cash was historically recorded only when banked. Future studio cash receipts will
be registered individually in cash accounts. Keep historical bank deposits as bank
movements, not fabricated studio receipts or a verified historical cash balance.
Blank Spanish studio assignments default to Estepona; additional studios require
an explicit selection. Missing expense classifications remain for review, including
missing periods rather than guessing the payment month. The owner confirmed the
three date errors and approved the proposed May9/May10/May12 corrections.

## Implementation

finance/spain_migration.py wraps the existing bounded native XLSX reader, leaving DR
interpretation intact. ES/EUR preview upload accepts a validated destination studio
for blank locations; auto-select only when exactly one existing studio is available.
Keep explicit nonblank workbook locations. Store the chosen default in the immutable
preview summary/row interpretation, not a hardcoded global Spain studio ID. Original
workbook bytes, cells and formulas are retained. Known approved date corrections are
guarded by original bank date, operation date, amount and terminal concept; raw cells
are not rewritten and each applied correction is shown in the preview.

Movement source currency is EUR, bank posting provider Caixa. Supervised migration
uses existing completion/review rules: mapped complete entries Reviewed; missing
period/category/subcategory/method or conflicting terminal assignments remain pending.
The workbook's Local category can resolve to the standard catalog's Local /
Instalaciones through its stable local catalog code. Other aliases are not invented.
The destination category catalog must be configured before preparing/importing if
existing classifications are to map. Do not auto-create or overwrite company settings
from the workbook's Datos template, which includes foreign terminal references.

All ES historical rows remain bank origin. The14 INGRESO CAJERO cash deposits become
internal movements. The two transfers labelled Efectivo are not proven internal or
customer receipts: preserve bank facts and leave their payment channel pending.
ES cash posting/recovery paths reject this workbook, and Alegra sales migration is
unavailable; authoritative sales remain existing Mindbody Analytics imports. UI shows
only the bank section for ES and displays actual currency, selected default studio,
original bank origin and corrected dates. Copying previews cannot cross currencies/
countries; ES previews cannot carry default studio IDs into another site.

Reuse normal bank commit/undo/history and migration permission. A unique exact
same date/amount/currency/direction/concept can link a Caixa historical expense that
lacks balance metadata, only when one side is explicitly historical, both occurrence
counts are unique and no nonempty metadata conflicts. Multiple indistinguishable
occurrences and existing classification conflicts still require explicit decisions.
Original routine bank matching and protected manual assignments remain intact.

## Evidence and local state

Full finance regression459 PostgreSQL tests passed before final completeness/alias
refinements; final22 migration/bank PostgreSQL tests passed, including ambiguous
same-fact occurrences and standard Local catalog mapping. Frontend production build
and changed-file lint passed; no schema migration required or drift detected.

Real-file rehearsal used a disposable copy of local data, not the working ledger:
588 selected rows ->494 new /84 unchanged /7 ambiguous /3 classification conflicts.
Commit created494 movements and left10 pending decisions; none of those ten became
new duplicate movements. Original94 routine Caixa movements were reused or held
for explicit review. Rehearsal took about1.5s on local SQLite; not a production
performance guarantee. No genuine duplicate occurrences were collapsed.

Saved working preview12 for QA spain company, defaulting to the existing configured
Caixa terminal studio QA Estepona. This is a local fixture name/ID, not production
setup. Preview has588 rows/three approved date corrections; no working movements
were posted. Destination company currently has no category catalog: owner should
initialize/import its shared catalog before preparing the bank import. Browser
verified ES upload/studio selector, bank-only preview controls, currency, totals and
all three correction notices. New paginated text shows pages and item counts apart.
Local frontend3037/backend8027 were restarted and verified responding.

## Owner tests

1. Open http://127.0.0.1:3037/loginPage. Existing local test credentials unchanged.
2. Settings -> Categories: configure QA spain company's shared catalog using the
   existing starting-catalog or CSV transfer workflow; do not overwrite other companies.
3. Initial setup -> QA spain company -> preview12. Inspect interpreted locations,
   missing periods/classifications, source cells and three May correction notices.
4. Select Caixa destination and eligible rows; confirm bank origin and review the
   plan before posting. Existing assignments/ambiguous matches remain explicit review
   decisions. Inspect those decisions rather than treating them as new transactions.
5. Inspect imported records: complete mapped entries Reviewed, incomplete expenses
   pending, ATM cash deposits internal on Caixa, two cash-labelled transfers pending.
   Existing manually recorded actual cash stays independent.
6. Repeat the same migration preview/import; linked evidence must not create extra
   transactions, and original files/cells remain available. Resolve any genuine
   ambiguous occurrences using the existing review flow, without inventing balances.

Step4 still awaits owner acceptance and any required real-refund source validation.
Negative/refund safety is tested synthetically and remains pending review; source
refund accounting is not certified from the provided positive-only samples. Step5
release readiness has not begun. Wait for explicit commit/progression instructions.
