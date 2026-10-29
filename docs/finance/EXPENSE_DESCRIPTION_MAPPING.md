# DR expense description mapping

2026-10-29 · Owner-confirmed correction before committing the operational MVP.

The historical Debitos worksheet uses **Concepto** for the bank transaction text and
**Descripción Original** for the owner's expense description. The original v1
importer interpreted those headers backwards. This is an import interpretation defect;
swapping table cells alone would leave editing and future routine bank matching wrong.

The v2 workbook reader maps Concepto → `original_description` → movement source
`description` (**Bank concept**) and Descripción Original → `manual_description` →
classification `description` (**Description**). Income mapping is unchanged. Labels
are Bank concept / Description in English and Concepto bancario / Descripción in Spanish.

Existing v1 workbook bytes, raw cells and their stored parsed snapshot are retained.
`parsed_business_fields` provides the corrected business interpretation of v1 debit
rows for previews and future preparation. New uploads use parser v2. The audited
maintenance command corrects old derived bank preview descriptions and affected
ledger description fields, preserving amounts/dates/currency/balances, record IDs,
review state, category/subcategory/studio/period and original files. Later explicit
manual description edits and newer source text are preserved. Routine/manual records
are not indiscriminately swapped. Matching uses the corrected bank concept afterwards.

Back up the database, then preview/apply for the intended company and audit actor:

```sh
python manage.py repair_expense_descriptions --company COMPANY_ID --actor USER_ID
python manage.py repair_expense_descriptions --company COMPANY_ID --actor USER_ID --apply
```

Default preview rolls back. Application is idempotent and records
`description_interpretation` events for changed preview rows and movements. This is
a controlled interpretation upgrade authorized by the owner, not a general UI bypass
for reviewed records. Existing record edit/reopen permissions continue to apply.
