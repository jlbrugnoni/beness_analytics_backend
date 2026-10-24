# Phase 2.2 category configuration discovery

Date: 2026-10-24. Phase 2.1 accepted; Phase 2.2 business questions pending.
No category models, API or UI have been implemented at this checkpoint.

## Workbook evidence

Read-only extraction from Ingresos_Egresos_DO_BI.xlsx, Datos!P2:Q45, found
10 categories and 44 explicit category/subcategory pairs. The debit sheet uses
one extra meaningful pair: Otros / Extraordinarios. It also contains one
invalid-looking category/subcategory pair, 1 / 1. Keep that source value for
migration review; do not silently convert it to an expense category.

Other helper lists differ: Personal includes Prestaciones and Vacaciones,
whereas the explicit paired catalog uses Vacaciones / liquidaciones. Do not
merge or substitute helper values automatically. Existing file transactions
and their descriptions were not copied into this repository.

| Category | Subcategories from explicit paired catalog |
| --- | --- |
| Personal | Sueldos; Seguridad social; Honorarios; Comisiones; Vacaciones / liquidaciones; Dietas y Viaticos |
| Local / Instalaciones | Alquiler; Comunidad; Mantenimiento; Limpieza; Seguro |
| Servicios | Electricidad; Agua; Internet y telefono; Valet parking; Otros |
| Operacion | Equipamiento; Mantenimiento equipos; Materiales; Insumos; Uniformes |
| Marketing | Publicidad digital; Diseño; Impresiones; Promociones |
| Software | Mindbody; Alegra; Otras suscripciones |
| Administracion | Contabilidad; Legal; Impuestos; Sueldos administración; Seguridad social administración; Transporte administración; Caja chica administración; Otros gastos administración |
| Bancos | Comisiones; TPV / POS; Intereses; Devoluciones |
| Logistica | Envios; Transporte; Aduanas |
| Otros | Varios |

Source labels retain their spelling. Catalog names are financial configuration,
not raw source financial rows or personal payroll information.

## Q-008: client questions sent

1. Company ownership: recommend independent categories per company, with catalog
   copying as a later explicit operation. DR changes should not silently alter ES.
2. Sensitive defaults: recommend entire Personal category, plus Administracion /
   Sueldos administración and Seguridad social administración. Client to confirm
   additional sensitive categories/subcategories. Privacy behavior itself is
   already accepted in BR-037; do not reopen it.
3. Financial defaults: recommend operating for ordinary expenses, extraordinary
   for revenue-related Administracion / Impuestos, and review for Equipamiento,
   Bancos / Intereses and Bancos / Devoluciones. Client to confirm defaults.
   Large equipment and actual refund interpretation require movement evidence;
   a category name is not proof of a refund or an internal transfer.
4. Initial catalog: recommend explicit 10/44 paired list plus Otros /
   Extraordinarios. Preserve invalid 1 / 1 for migration review.

All four are proposals, not accepted defaults. Do not seed these recommended
settings or classify historical payments until answers arrive. Missing answers
must not be interpreted as approval.

## Already accepted boundaries

- Editable names and additional categories/subcategories through application UI.
- Preserve stable references; deactivate rather than hard-delete.
- Parent sensitivity applies to children. Extra sensitive-detail capability and
  financial settings permission are required for sensitivity changes. Never
  make an inherited-sensitive child public by unchecking its own flag.
- Category names/configuration are distinct from identifying payment details.
  Transaction/detail redaction across API/search/export/raw/history remains a
  later-processing acceptance task (A-28), not complete just because flags exist.
- Operating versus extraordinary is distinct from shared/direct allocation.
  Administration is allocated by accepted expense-month gross-sales policy;
  a default cannot overwrite existing explicit studio assignments on migration.
- Defaults are configuration guidance, not automatic restatements of history.
- Reuse financial gates, scope checks, atomic audit/revision behavior from 2.1.
  Decide implementation details without requesting client technical approval.
- Imports, movement categorization, allocations and results remain later phases.

## Next implementation after answers

Implement editable taxonomy, inherited sensitive/active state, default treatment
and allocation guidance, scoped writes, duplicate/parent integrity checks, audit
and stale edits; add EN/ES configuration UI. Verify cross-company scope and
sensitive-flag protections with tests, then isolated local browser QA and client
acceptance. Remain on feature/finance-phase-2 in both repositories.
