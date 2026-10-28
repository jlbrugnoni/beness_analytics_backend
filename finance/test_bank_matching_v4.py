"""Four-fact identity, recurring Popular IDs and audited pending recovery."""
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_bank_posting as fixtures
from .models import BankPosting, BankDecision, BankMovement, BankMovementClassification, BankEvent


@override_settings(FINANCE_ENABLED=True)
class BankMatchingV4Tests(APITestCase):
    setUp=fixtures.BankPostingTests.setUp
    upload=fixtures.BankPostingTests.upload
    preview=fixtures.BankPostingTests.preview
    processing=fixtures.BankPostingTests.processing
    commit=fixtures.BankPostingTests.commit
    post=fixtures.BankPostingTests.post
    resolve=fixtures.BankPostingTests.resolve

    def csv(self,*rows):
        return '\n'.join(fixtures.POPULAR.splitlines()[:3])+'\n'+'\n'.join(rows)+'\n'

    def pending(self,source):
        batch=self.preview(source)
        posting=BankPosting.objects.create(batch_id=batch,actor=self.user)
        for row in posting.batch.rows.filter(kind='data'):
            BankDecision.objects.create(posting=posting,row=row,outcome='ambiguous')
        return batch

    def apply(self,batch,token=None):
        return self.client.post(f'/api/finance/bank-imports/{batch}/apply-pending/',
            {'expected_plan':token or self.processing(batch)['token']},format='json')

    def test_terminal_party_serial_and_generic_references_do_not_match_across_days(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,123456789,0039618800006,AZUL',
                           '01/09/2026,Débito Cuenta,20.00,180.00,1,0000000000001,Expense',
                           '01/09/2026,Crédito Transferencia,50.00,230.00,,0000776250730,Transfer'))
        batch=self.preview(self.csv('16/09/2026,Crédito Transferencia,100.00,300.00,987654321,0039618800006,AZUL',
                           '16/09/2026,Débito Cuenta,20.00,280.00,1,0000000000001,Expense',
                           '16/09/2026,Crédito Transferencia,50.00,330.00,,0000776250730,Transfer'))
        self.assertEqual(self.processing(batch)['counts'],{'new':3})
        self.commit(batch)
        self.assertEqual(BankMovement.objects.count(),6)

    def test_same_day_amount_description_with_distinct_balances_are_separate_occurrences(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL'))
        batch=self.preview(self.csv('01/09/2026,Crédito Transferencia,100.00,300.00,,TERMINAL,AZUL'))
        self.assertEqual(self.processing(batch)['counts'],{'new':1})
        self.commit(batch)
        overlap=self.preview(self.csv('01/09/2026,Crédito Transferencia,100.00,300.00,,TERMINAL,AZUL',
                                     '01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL'))
        self.assertEqual(self.processing(overlap)['counts'],{'unchanged':2})

    def test_missing_balance_and_indistinguishable_repeated_occurrences_stay_pending(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,,,TERMINAL,AZUL'))
        batch=self.preview(self.csv('01/09/2026,Crédito Transferencia,100.00,,,TERMINAL,AZUL',
                                    '16/09/2026,Crédito Transferencia,50.00,250.00,,,New transfer'))
        self.assertEqual(self.processing(batch)['counts'],{'ambiguous':1,'new':1})
        batch=self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,,,TERMINAL,AZUL',
                                '01/09/2026,Crédito Transferencia,100.00,,,TERMINAL,AZUL'))
        self.assertEqual(self.apply(batch).data['changed'],{})
        self.assertEqual(self.processing(batch)['pending_count'],2)

    def test_missing_metadata_with_same_four_facts_links_but_conflicting_facts_require_review(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,,AZUL  settlement'))
        batch=self.preview(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,123456789,TERMINAL,AZUL settlement'))
        self.assertEqual(self.processing(batch)['counts'],{'unchanged':1})
        changed=self.preview(self.csv('01/09/2026,Crédito Transferencia,110.00,200.00,123456789,TERMINAL,AZUL settlement'))
        self.assertEqual(self.processing(changed)['counts'],{'correction':1})

    def test_multiple_same_day_terminal_settlements_with_different_amounts_are_new(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL'))
        batch=self.preview(self.csv('01/09/2026,Crédito Transferencia,50.00,250.00,,TERMINAL,AZUL'))
        self.assertEqual(self.processing(batch)['counts'],{'new':1})

    def test_multiple_metadata_variants_cannot_automatically_claim_one_existing_occurrence(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,,AZUL'))
        batch=self.pending(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,123456789,TERMINAL,AZUL',
                                    '01/09/2026,Crédito Transferencia,100.00,200.00,987654321,TERMINAL,AZUL'))
        self.assertEqual(self.processing(batch)['counts'],{'ambiguous':2})
        self.assertEqual(self.apply(batch).data['changed'],{})
        self.assertEqual(BankMovement.objects.count(),1)

    def test_pending_source_correction_never_applies_in_bulk_and_requires_a_reason(self):
        self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL'))
        batch=self.pending(self.csv('01/09/2026,Crédito Transferencia,110.00,200.00,,TERMINAL,AZUL'))
        row=self.processing(batch)['rows']['results'][0]
        self.assertEqual(self.apply(batch).data['changed'],{})
        self.assertEqual(self.resolve(batch,row,'correct',BankMovement.objects.get(),note='').status_code,400)
        self.assertEqual(BankMovement.objects.get().source['amount'],'100.00')

    def test_recovery_preserves_prior_work_and_is_audited_stale_safe_and_retry_safe(self):
        first=self.post(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL'))
        movement=BankMovement.objects.get();movement.classification.description='Partner classification';movement.classification.save()
        source=movement.source.copy();classification=list(BankMovementClassification.objects.values())
        batch=self.pending(self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL',
                                    '16/09/2026,Crédito Transferencia,50.00,250.00,,TERMINAL,AZUL'))
        state=self.processing(batch);self.assertEqual(state['ready_counts'],{'new':1,'unchanged':1})
        result=self.apply(batch,state['token']);self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['changed'],{'link':1,'create':1})
        movement.refresh_from_db();self.assertEqual(movement.source,source)
        self.assertEqual(list(BankMovementClassification.objects.filter(movement=movement).values()),classification)
        self.assertEqual(BankDecision.objects.get(posting__batch_id=first).resolution,'created')
        self.assertEqual(self.apply(batch,state['token']).status_code,409)
        self.assertEqual(self.apply(batch).data['changed'],{})
        self.assertEqual(BankMovement.objects.count(),2)
        self.assertEqual(BankEvent.objects.filter(posting__batch_id=batch,action='create',actor=self.user).count(),1)

    def test_filtered_pending_queue_excludes_completed_rows_and_permission_is_rechecked(self):
        batch=self.pending(self.csv('16/09/2026,Crédito Transferencia,50.00,250.00,,TERMINAL,AZUL'))
        self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.apply(batch).status_code,403)
        self.profile.can_edit_finance=True;self.profile.save();self.apply(batch)
        result=self.client.get(f'/api/finance/bank-imports/{batch}/processing/?pending=1')
        self.assertEqual(result.data['rows']['count'],0);self.assertEqual(result.data['pending_count'],0)

    def test_recovery_never_assigns_two_rows_to_the_same_previously_used_movement(self):
        source=self.csv('01/09/2026,Crédito Transferencia,100.00,200.00,,TERMINAL,AZUL')
        self.post(source)
        batch=self.pending(source)
        decision=BankDecision.objects.get(posting__batch_id=batch)
        # A previously confirmed row in this posting already owns this occurrence.
        from .models import BankImportRow
        other=BankImportRow.objects.create(batch_id=batch,row_number=99,source_line=99,source_line_end=99,kind='data',parsed=decision.row.parsed)
        BankDecision.objects.create(posting=decision.posting,row=other,outcome='unchanged',resolution='linked',movement=BankMovement.objects.get())
        self.assertEqual(self.apply(batch).data['changed'],{})
        self.assertEqual(BankMovement.objects.count(),1)
