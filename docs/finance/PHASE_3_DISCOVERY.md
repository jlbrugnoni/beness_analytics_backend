# Phase 3 imports and historical migration discovery

Date: 2026-10-24. Phase 2.4 accepted (D-042). Q-011 sent; answers pending.
This is discovery and development sequencing, not delivered import functionality.

## Accepted behavior to preserve

- Finance owns financial batches, movements and reconciliation. Existing
  core_data.ReportImport/SaleLine and operational import routes remain intact.
  Reuse appropriate parsing primitives only after checking semantics; do not
  mix finance files into existing operational report types.
- Popular separates debits and credits. Dates need not be globally sorted.
  Caixa uses signed EUR amounts. Preserve original rows and observed references;
  reference presence is not proof of global uniqueness.
- Retries/reordered/overlapping files must not duplicate the same movement;
  genuine repeated identical movements must remain possible. Do not use a
  date/description/amount hash as a global unique transaction key.
- Original versus assigned values and creation origin are separate. Preserve
  manual dates, categories, studio/channel decisions and source filename/history.
  Missing rows in a later partial file never mean automatic deletion.
- Missing assignments and ambiguous identity are review work, not reasons to
  reject independent valid rows. Missing required amount/date/currency cannot
  produce a fabricated movement. Preview must distinguish file errors, invalid
  rows and unresolved business assignments.
- DR sales use item-level Alegra grouped by invoice, counted once. Spain reads
  existing Mindbody sales later; no duplicate routine Spain sales upload.
- Enriched historical migration is separate from raw imports, preserving existing
  assignments and surfacing raw overlap without losing manual work.
- Access, account scope, bank/sensitive detail, raw previews/downloads and batch
  histories must be protected together. Import capability cannot bypass another
  detail restriction. No raw report is committed to Git.

## Q-011: questions sent

1. For bank reports, do you usually download the whole month again, only new
   dates, or overlapping periods? Does this differ between Popular and Caixa?
2. For Alegra exports, do you always include every invoice item for the selected
   dates, or sometimes filter by product/category/payment method? This affects
   recognizing corrected invoices without removing valid items.
3. Which period should be the first historical migration test? Recommend one
   completed DR month with classified workbook entries and raw bank/Alegra reports
   so totals can be compared. Existing September 1–15 samples still support
   adapter validation; a full-month pilot is a separate choice.
4. Should an upload made by mistake support audited undo? Proposal: undo untouched
   records created by that upload; require review for later manually edited or
   reconciled records; preserve existing records merely encountered again.

## Intended delivery sequence

1. **3.1 and initial 3.2: bank preview/history foundation.** Popular and Caixa
   CSV readers, explicit company/account/provider context, retained lineage,
   parsed counts/direction totals/issues and a read-only preview. No financial
   commit claimed until its persistence and scope checks are implemented.
2. **3.2 and initial 3.5: bank commit/overlap review.** Immutable source evidence,
   financial movements, atomic stale-preview checks, retry/occurrence handling,
   ambiguous identity review and audit. Implement rollback/undo only after the
   client answers Q-011. Never remove an existing record because it is absent
   from a partial upload. Do not silently merge indistinguishable occurrences.
3. **3.3: Alegra invoice/item imports.** Validate invoice identity, totals,
   complete-versus-filtered export semantics and source corrections before
   replacing any previously observed items. Preserve individual item occurrences.
4. **3.4 and remaining 3.5: historical enriched migration.** Map existing columns
   and studios/categories, preserve client dates/classifications, compare totals
   and link subsequent raw reports. Agree the pilot period/cutoff from Q-011 and
   actual file coverage. Do not claim migration is complete from a partial sample.

Each delivery gets focused tests, documentation and a client checklist before
advancing. Broad phase agreement is not approval of unanswered business cases.

## Evidence and technical preparation

Reviewed core_data/importers.py and ReportImport metadata: existing operational
report types include attendance, sales, sales-by-service and availability, not
bank reports. ReportImport stores filename/hash/uploader/time; financial lineage
needs its own model and scope-aware surface. Existing finance configuration and
source interpretation helpers are available; no movement/import model exists yet.

Known reference facts remain A-01 and other roadmap scenarios, not newly passed
financial import tests. The Popular sample has 175 movements (100 credits and
75 debits), and the supplied Alegra report covers September 1–15, 2026. These
partial-period fixtures cannot establish a complete monthly result.

No code, migrations, real uploads, data/grant changes or production changes in
this discovery checkpoint. Both repositories remain on feature/finance-phase-2;
branch naming is historical and does not imply any phase was deployed.
