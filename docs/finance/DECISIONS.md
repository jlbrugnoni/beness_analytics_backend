# Finance decision log

Use stable decision IDs. Record changes as a new dated entry referencing the
superseded decision; never rewrite history to suggest an earlier assumption was
client-approved. Detailed behavior belongs in Business rules.

| ID | Date | Status | Decision and basis |
| --- | --- | --- | --- |
| D-001 | 2026-10-24 | Accepted | Client agreed to the phased finance plan: separate Django app, shared existing studios/users, explicit finance access, configuration, review, reconciliation, results, and pilot. See BR-001–003, BR-029–031. |
| D-002 | 2026-10-24 | Accepted | Client normally invoices in Alegra when paid; invoice date defaults payment date. Use cost center for studio and flag contradictory studio price lists; General is neutral. See BR-004–007. |
| D-003 | 2026-10-24 | Accepted | Item-level Alegra report is the routine sales source; group by invoice while retaining items. No routine second Alegra report is required for the agreed manual-channel workflow. See BR-005–007. |
| D-004 | 2026-10-24 | Accepted | Caixa terminal 369092994 belongs to Estepona; final DDMM in ON descriptions is operation day/month. Confirmed directly by client. See BR-012. |
| D-005 | 2026-10-24 | Accepted | Historical enriched tables need a migration importer with existing assignments; retries and overlapping raw uploads must preserve records and manual work. See BR-022–028. |
| D-006 | 2026-10-24 | Accepted | Developer works as a delivery partner: asks phase business questions, maintains project documentation, reports What I did / What you should test, and records progress for future agents. No external review agent requested. |
| D-007 | 2026-10-24 | Accepted | Client identified Bewellness Group SL as Spain's company/Caixa owner. Initial account register remains pending. See Q-001/BR-003. |
| D-008 | 2026-10-24 | Accepted | Client requested explicit internal movements for deposited cash and Dominican operating-to-savings transfers. Cash should already be recorded as sales. Precise final-result presentation and cash controls remain pending. See Q-002/BR-014. |
| D-009 | 2026-10-24 | Accepted | Client confirmed AZUL deposits arrive net of processing fees; reconciliation subtracts the configured channel fee from gross Alegra sales before comparing. Separate transfer fees also exist. Monthly fee basis and nature of separate AZUL debits remain pending. See Q-003/BR-019. |
| D-010 | 2026-10-24 | Accepted | Client accepted separate display of own-company internal movements and exclusion of principal from profit; associated bank fees remain expenses. Resolves the presentation left open in D-008. See P-001/Q-002/BR-014. |
| D-011 | 2026-10-24 | Accepted | Client accepted estimated processing fees with later actual adjustments plus distinct charged fees. Resolves the monthly basis left open in D-009; individual AZUL debit classification remains open. See P-002/Q-003/BR-019. |
| D-012 | 2026-10-24 | Client direction accepted; technical design selected | Client prefers the existing internal-partner permission workflow (groups, allowed sites, money flag, individual permissions) and delegated group-versus-user design choice. Use editable group capability sets plus additive user grants and existing location limits. Supersedes separate per-studio finance-role assignments in the earlier architecture/BR-031; different action levels by studio are deferred. Exact technical-superuser/account-detail policy remains open. See Q-004/BR-029–031. |
| D-013 | 2026-10-24 | Accepted | Client classifies company-wide expenses as administration and later allocates them to studios by weighted income. Preserve company source expense and allocations without double counting. See Q-005/BR-018/BR-032. |
| D-014 | 2026-10-24 | Accepted | Client selected gross sales before processing fees, using the expense's assigned month. If there is no income, leave allocation pending with a manual split available. Completes D-013's main formula inputs. See Q-005/BR-032. |
| D-015 | 2026-10-24 | Accepted | Client requested configurable sales tax and supplied initial settings: Spain sales include 21% IVA; Dominican activity has no sales tax. Use company defaults/effective dates while retaining source tax and exceptions. This is client-provided setup; monthly tax presentation and expense tax remain open. See Q-006/BR-033. |
| D-016 | 2026-10-24 | Accepted | Client selected a basic tax-inclusive result for v1; expense tax and net-to-net comparison are deferred. Gross sales including IVA before fees are also the v1 administration base. Tax configuration/source metadata remain in scope. Resolves D-015's result presentation; the earlier excluding-IVA recommendation was not adopted. See Q-006/BR-034. |
| D-017 | 2026-10-24 | Accepted direction; label recommended | Configure DR first. Proposed editable name Banco Popular - Cuenta operativa (DOP). History starts January 2026 in DR; Spain expenses mid-2025, income February 2026. Exact coverage comes from files; no accounts created yet. BR-003/BR-036. |
| D-018 | 2026-10-24 | Accepted | Manual creation and report uploads both required, with manual/import origin and report name. Seed workbook categories and allow in-app category/subcategory maintenance. BR-002/BR-035. |
| D-019 | 2026-10-24 | Accepted | Unknown AZUL debits stay for review. Caixa first-year terminal fees are charged and separately reimbursed; retain debit and credit, linking reviewed fee offsets. BR-039. |
| D-020 | 2026-10-24 | Accepted | V1 uses Mindbody Sales for Spain and Alegra for DR. Alegra remains the future Spain target; no cutover date. Future Spain consumer invoice support must permit missing customer names. BR-008. |
| D-021 | 2026-10-24 | Accepted | Refund reduces original sale month's result; preserve actual refund date and linkage without duplicate cancellation effects. BR-038. |
| D-022 | 2026-10-24 | Accepted | Final management result = operating + extraordinary inflows - extraordinary outflows. Loan receipts increase final only. Revenue-related taxes are non-operating; employment taxes/contributions are operating. Map exact tax categories during setup. BR-020. |
| D-023 | 2026-10-24 | Client direction accepted; technical design selected | Sensitive category flag with extra group/user capability. Without it show authorized aggregates, not individual sensitive payments; protect API/export/download paths. Keep Django superuser technical administration; ordinary Admin group needs explicit finance grants. BR-031/BR-037. |
| D-024 | 2026-10-24 | Deferred for initial use | Prepare period/history structure; enforced closing/reopening is for later adoption. No hard month locks or mandatory closing UI in initial v1. BR-021. |
| D-025 | 2026-10-24 | Developer-selected default | Client delegated tolerance: configurable 0.01 DOP/EUR rounding-review threshold, with explicit confirmation and no automatic write-off or hidden amount changes. BR-040. |
| D-026 | 2026-10-24 | Accepted | Client replied "perfect, we can continue" to Phase 0 review handoff. Phase 0 accepted and Phase 1 foundation/access authorized. No production deployment authorized. |

| D-027 | 2026-10-24 | Accepted | Client confirmed "great, it works properly" after reviewing Phase 1 in the isolated local preview. Phase 1 accepted; proceed to Phase 2 configuration discovery under the existing phased working agreement. No production deployment authorized. |

| D-028 | 2026-10-24 | Accepted | Client accepted the proposed Dominican operating/savings account labels, wants expected savings balance despite no statements, and confirmed zero at the start of the year (2026 historical context). Record 0.00 DOP at start of 2026-01-01; later migration supplies internal transfers. Expected and bank-verified balance must remain distinct. See BR-041/INITIAL_CONFIGURATION.md. |
| D-029 | 2026-10-24 | Accepted | Client supplied eight Dominican terminal/studio/type mappings. Preserve the exact table in INITIAL_CONFIGURATION.md; it supersedes illustrative examples. No Arroyo Hondo recurring terminal was supplied. |
| D-030 | 2026-10-24 | Accepted | Cierre (credit/debit) and Recurrentes have 3.5% withholding; Link 5%. Client says these have applied "since forever": historical baseline throughout available coverage, no invented contract start date. Fee-rule configuration/processing remains later work. |

| D-031 | 2026-10-24 | Accepted | Client replied "perfect, we can continue" after Phase 2.1 accounts/terminals handoff. Phase 2.1 accepted; proceed to Phase 2.2 discovery and implementation under the phased working agreement. No production push/merge/deployment authorized. |

| D-032 | 2026-10-24 | Accepted | Independent catalogs per company, while aiming to use the same categories for comparable analysis. Start each company from the same baseline; preserve stable shared catalog codes across those initial copies. Company edits do not propagate automatically. Custom cross-company mapping/copying can be added later. |
| D-033 | 2026-10-24 | Accepted | Initial sensitivity: entire Personal category, plus Administracion / Sueldos administración and Seguridad social administración. No additional categories requested. Inherited protection and the existing extra capability policy remain in force. |
| D-034 | 2026-10-24 | Accepted | Ordinary expenses default operating; revenue-related Administracion / Impuestos extraordinary; Operacion / Equipamiento, Bancos / Intereses and Bancos / Devoluciones require individual review. Defaults guide classification; they do not establish a refund, loan or actual allocation from a label. |
| D-035 | 2026-10-24 | Accepted | Start from the workbook's 10-category/44-pair explicit catalog plus Otros / Extraordinarios (45 subcategories total). Invalid source category/subcategory 1 / 1 remains a migration review issue. Preserve source names; initial Extraordinarios default is extraordinary. |

| D-036 | 2026-10-24 | Accepted | Client confirmed "perfect, it worked good. we can continue" after Phase 2.2 category handoff. Phase 2.2 accepted; proceed to Phase 2.3 discovery under the phased working agreement. No production deployment authorized. |

| D-037 | 2026-10-24 | Accepted | Client clarified Alegra conventions: Tarjeta débito = Link, Tarjeta crédito = Cierre, Efectivo = cash, Transferencia = transfer. Recurring payments also use Tarjeta crédito and must be distinguished manually. Default credit to Cierre with review required; a per-record manual recurring correction takes precedence without rewriting the source label. This supersedes Q-009's proposal to leave generic card channels entirely unassigned. |
| D-038 | 2026-10-24 | Accepted | Spain currently has no recurring or transfer payments; clients normally use in-studio card and cash. Configure these as the initial operational channels. Exact Mindbody exported method names were not supplied, so do not invent aliases or reuse DR Alegra names. Support editable mappings and future channels without implying they are presently used. |

| D-039 | 2026-10-24 | Accepted | Client confirmed "it looks good" after the Phase 2.3 mapping handoff. Phase 2.3 accepted; proceed to Phase 2.4 fee/settlement/tax discovery under the phased agreement. No production deployment authorized. |

| D-040 | 2026-10-24 | Accepted | Caixa currently deposits the full card-sales amount. Its terminal-use fee is charged separately and later reimbursed. Client estimates around EUR 36 and says the offer ends in 2027; exact amount, frequency and dates remain unconfirmed, so do not create an exact recurring expense or offer expiry from these approximations. |
| D-041 | 2026-10-24 | Accepted | DR deposits normally take 24–48 hours and may take longer over weekends. Use typical elapsed-hour timing for Cierre, recurring and Link suggestions, without silently changing operation dates or claiming holiday-aware due dates. |

| D-042 | 2026-10-24 | Accepted | Client replied "we can continue" after the Phase 2.4 delivery and test checklist. Phase 2.4 accepted; proceed to Phase 3 import/migration discovery under the agreed phased workflow. No production push, merge or deployment authorized. |

| D-043 | 2026-10-24 | Accepted | Popular reports are normally downloaded daily due to volume, and overlapping downloads are allowed to ensure coverage. Caixa is downloaded every several days. Bank ingestion must support overlaps; download frequency is not a completeness guarantee. |
| D-044 | 2026-10-24 | Accepted | Client downloads all Alegra invoices without product/category/payment-method filtering. Treat routine exports as the full selected-date invoice report, while validating actual invoice completeness/correction semantics in Phase 3.3. Absence from a partial period is not deletion. |
| D-045 | 2026-10-24 | Accepted approach; exact month pending | Client accepted using one completed DR month with classified workbook entries and raw bank/Alegra reports for the first historical migration comparison. No particular month or cutoff was selected. Choose it during migration preparation; September 1–15 samples remain partial adapter fixtures. |
| D-046 | 2026-10-24 | Accepted | Client accepted audited undo for an erroneous upload: undo untouched financial records created by that upload; require review for records edited/reconciled afterwards; preserve pre-existing records merely encountered again. Detailed source-update reversals need case validation at commit/overlap implementation. Raw preview history is not financial posting and is not deleted by this policy. |
| D-047 | 2026-10-24 | Developer implementation of existing privacy policy | Unclassified bank source files may contain sensitive payroll. Bank preview/history/raw-row reads therefore require full-account and sensitive-detail access alongside financial view/money. Creating previews and retrieving original files additionally require import capability. This enforces D-023/BR-037 before category-aware transaction redaction exists; it does not grant any real users new access. |

| D-048 | 2026-10-24 | Accepted | Client confirmed "perfect. it worked well" after Phase 3.1 bank-preview testing. Phase 3.1 accepted; proceed to Phase 3.2 transaction commit/overlap/undo discovery. Production deployment remains unauthorized. |

| D-049 | 2026-10-24 | Accepted | Client answered yes to Q-012. Operators may undo their own financial imports; users with Manage financial configuration may also undo others' imports. Relevant import/edit permissions and account scope are required for everyone, and managers do not bypass protected-record safeguards. Implementation treats ownership as the user who committed the financial posting, recorded separately from the raw file uploader. |
| D-050 | 2026-10-24 | Accepted | Client answered yes to Q-012 correction policy. Keep the current transaction when later bank evidence proposes a changed amount/date; replacement requires explicit review/approval. Independent valid new rows continue importing. Preserve old source evidence, manual work and history. |
| D-051 | 2026-10-25 | Accepted | Client said "we can continue" after Phase 3.2 delivery/testing. Bank transaction posting, correction review and audited undo accepted. Proceed to Phase 3.3 Alegra invoice/item discovery; no finance deployment authorized. |
| D-052 | 2026-10-25 | Accepted | Q-013: invoice numbers should not repeat in either company. DR uses B01/B02 plus eight digits. Identity includes company/source/full prefixed code; do not assume yearly reuse. |
| D-053 | 2026-10-25 | Accepted | Q-013: approval required for changed invoice evidence. Client states Alegra allows cancellation but cannot modify date, amount or client. Keep those original values; unexpected changes are anomalies for investigation, not normal editable fields. Preserve old evidence/manual work. Status approval belongs to posting, not source preview. |
| D-054 | 2026-10-25 | Accepted | Q-013: current invoices do not use mixed payment methods. A client may use one or two cards at the same moment; daily bank settlement aggregates them. V1 does not require per-card splits for an invoice. |
| D-055 | 2026-10-25 | Accepted; exact label pending | Q-013: cancelled invoices remain in Alegra with cancelled status; later refund appears as a bank debit. Apply BR-038 once in the original sale month and link bank refund separately. Exact ESTADO cancellation text was not supplied; unknown statuses stay for review. |
| D-056 | 2026-10-25 | Accepted | Client confirmed "it worked well" after Phase 3.3.1 Alegra source-preview testing. Preview accepted; proceed to Phase 3.3.2 sales-posting/overlap/cancellation discovery. Exact cancelled ESTADO text remains unconfirmed. No finance deployment authorized. |
| D-057 | 2026-10-25 | Accepted | Q-014: exact Alegra cancellation status is Anulada. Cobrada is paid; unknown statuses stay for review. Resolves D-055/Q-013 exact-label dependency. |
| D-058 | 2026-10-25 | Accepted | Q-014: cancellation/reissue without returning client money can happen. Do not infer refund obligation or payment from cancellation alone. Preserve original-period sale treatment and record separate settlement/replacement evidence without a fabricated bank debit or double deduction. |

## Open policy decisions

| Topic | Discovery reference | Dependency |
| --- | --- | --- |
| Editable additional accounts/provider dates/tax-category mapping | Q-001/Q-003/Q-005 | Phase 2 setup |
| Verified cash balances/opening balances | Q-002 | Optional later balance requirement; manual entries are in v1 |
| Refund/non-positive income, source correction, rounding | Q-005 | Detailed Phase 4/5 validation |
| Actual-fee adjustment period for late evidence | Q-003 | Phase 5/6 case definition |
| Mindbody paid/refund/split-method source verification | Q-006 | Spain adapter acceptance; initial source is decided |
| Enforced closing and net-of-tax results | D-024/D-016 | Deferred; not initial-v1 blockers |

The main discovery batch is resolved. Detailed implementation questions must
reference a specific remaining case rather than reopen settled policy.
