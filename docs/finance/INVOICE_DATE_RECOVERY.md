# Invoice date correction and recovery without reset

Delivered locally2026-10-28, D-093; client acceptance pending.

## Actual diagnosis: migration10 / April23

Both current workbooks (migration10 and11) parse14 April23 invoices as2026-04-23,
without date issues. They are B0200002141–B0200002153 plus B0100000123; invoice item
rows2455–2470 in Alegra (16 items). Original date cells are numeric46135, correctly
read as April23,2026. Normalized invoice facts are identical across the two uploads.

The corresponding Alegra_adm payment rows2268–2281 have absent columnC (Numero)
cells in both uploaded workbooks. Parsed dates are valid2026-04-23; rejection is
missing_payment_number. No receipt was posted for those14 rows. Need real Alegra
payment/transaction numbers or a fresh transactions export; invoice codes are not
substitutes. The reader must not invent stable payment IDs from invoice references.

Sales import12 (migration10) is partial_undo, sales13 (migration11) undone. The undo
reversed46 unlinked invoices, including those14;4,949 active invoices remain. Existing
payments protected their linked invoices. This explains missing active April23
invoices despite valid source dates. No date parser change is needed for these cells.

## Standing correction/recovery workflow

- A date-only correction from a newer imported report can be explicitly approved
  after posting that report leaves the changed source pending. Exact company/provider/
  invoice identity, amount, customer, items, source fields and status must agree except
  date. Dates remain protected from arbitrary direct entry in Records.
- Approval requires existing import+edit capabilities/full source visibility, a reason,
  active posting/pending decision, current company token and decision revision.
  Invoice or linked payment reconciliation blocks it. Existing permissions are reused.
- Only sale.source.date changes. Preserve original source file/preview, amounts,
  customer/items, assignments/studio/channel, payment facts and IDs. Invoice before/
  after audit records actor, time and reason. Reevaluate payment links; source digest
  invalidates any prior manual invoice/payment approval. Approved correction is protected
  from undo; subsequent correction needs another reviewed source.
- Daily Upload reports exposes Approve reported date correction for eligible pending
  rows, opening a comparison/reason dialog. Historical/advanced SalesPostingPanel has
  the same action in Review change. Other changed facts remain protected.
- After an invoice import is undone/partly undone, Initial setup → migration → Alegra
  offers Prepare invoice recovery preview. Reuses the existing payment preview;
  creates a fresh invoice preview only. Repeating preparation reuses the unposted
  preview. Standard import classifies active invoices as unchanged and missing/reversed
  ones as new; no automatic posting or reactivation, no bank reset.

## Verification and evidence

357 PostgreSQL finance tests passed, plus5 final correction/recovery cases after final
reconciliation/undo guards. Frontend changed-file lint and production build passed.
New tests cover exact date correction/audit/source preservation, rejected customer
changes, required reason, access, reconciliation/stale decisions/older reports,
approved-date undo protection and partial-undo recovery preserving payment assignments.

Private consistent snapshot/rehearsal:
.local-backups/invoice-date-recovery-20261028/{backup,rehearsal}.sqlite3.
Rehearsed recovery on copy:4,949 unchanged +46 new +2 invalid,4,995 active afterward.
All preexisting active invoice source/items/assignments/studio/channel, every payment
source/assignment/link and bank movement source preserved. Existing payment batch12
reused. These results describe the copy; no recovery was posted on the working database.
Browser verified migration10 recovery button/explanation; left it for owner confirmation.

Owner steps: prepare/review/confirm invoice recovery, then supply actual missing payment
numbers in Alegra_adm C2268:C2281 (or a fresh Alegra transactions report), upload corrected
source and post payments. Existing payment identities are reused; only newly valid ones
are added. No full reset, automatic financial exception acceptance or synthetic IDs.
Local8027/3037 running. No production changes, merge, push, deployment or grant changes.
