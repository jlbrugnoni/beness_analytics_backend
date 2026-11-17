# Spain migration audit — 2026-11-16

Owner completed migration preview12 into Caixa batch29/posting21. Read-only audit
of local working data; no source decisions, assignments or financial facts changed
by the audit. Work remains uncommitted on feature/finance-spain-v2.

## Financial completeness

359 bank expenses total EUR233,760.79;229 bank incomes total EUR233,761.52. Both
counts and signed amounts match the interpreted workbook exactly. Full multiset
comparison of bank date/amount/currency/direction/concept matches source588 versus
ledger588, including repeated occurrences. No extra or missing bank transactions
were found. This is import completeness, not certified running balance or profit.

Posting results:494 created,84 linked,10 pending. Nonempty expected business
assignments match actual values for all created/linked rows. Existing bank source
balances and classifications were retained.55 destination categories now exist.
153 expenses and201 incomes are Reviewed;206 expenses and28 incomes need review.
Missing-category159, missing-period195 and missing-subcategory3 expense issues include
seven unlinked pending expenses; underlying source omissions were152 categories and
188 periods. Review reason counts overlap and must not be added as distinct entries.

Three approved May dates match the interpreted source and ledger. Original source
cells remain unchanged.11 of14 cash-labelled ATM deposits are internal movements;
three already-existing deposits still await classification confirmation. Other ATM
credits with different/unknown source methods remain pending as appropriate.

## Pending decisions and code refinement

Found three false ambiguities: same-day bank concepts shared by transactions with
different amounts. Caixa historical matching now filters compatible candidates by
all transaction facts before deciding uniqueness. Differing amounts no longer prevent
an otherwise unique match. Irrelevant candidates are removed from the exact-match
review list; real indistinguishable occurrences stay pending. Added regression test;
42 targeted bank/migration cases passed on PostgreSQL, frontend edit-file lint passed.

Ten saved decisions remain pending; refreshing the plan now gives:

-3 ready unchanged links: Debitos337 (Sep30,305.89),357 (Oct30,448.68),358 (Oct30,305.89).
 They can use the existing apply-ready action; the audit did not apply it.
-4 genuine ambiguous rows: Debitos335/336 (Sep30,two448.68 entries) and343/344
 (Oct13,two33.00 entries). Ledger has both occurrences; choose the intended one-to-one
 mapping rather than create new transactions. Workbook lacks their bank balances.
-3 movement-kind conflicts: Ingresos178 (Sep1,1020.00),202 (Sep28,1100.00),227
 (Oct28,2040.00). Routine imports gave these default Income; workbook interpretation
 proposes internal cash deposits. Keep financial facts; review/classify existing
 entries instead of duplicating them. Existing assignments are not overwritten.

## Cash test entry and closures

Manual entry6062 is on General cash EUR, amount12.00, operation date2026-10-02.
Its studio is empty; transaction date remains2026-11-15. If cash was actually received
Oct2, the owner should correct the transaction date and select the configured studio
(QA Estepona in this local fixture). The earlier bank-to-cash account edit cleared
studio. Fixed the manual editor to retain a selected studio compatible with the new
account; it still clears incompatible restricted assignments. The saved cash entry
was not changed by the audit.

October Card remains expected6692.60 / actual6732.09 / difference+39.49. Cash is
expected1841.65 / actual12.00 / difference-1829.65; company totals include unreviewed
cash with the corresponding review warnings. Local Mindbody imports contain April
and October examples, not all production history. Other monthly closure comparisons
need their authoritative Sales source data locally. Production was not accessed.

Step4 is still in acceptance/correction. No commit/push/deployment or Step5 work.
