"""Interpret DR expense description columns, retaining original workbook evidence."""

def parsed_business_fields(row):
    values=dict(row.parsed)
    # V1 read Concepto as the manual description, but this column is the bank's
    # concept. Descripción Original contains the owner's expense description.
    if row.kind=='debit' and row.batch.parser_version=='dr-enriched-xlsx-v1':
        values['original_description'],values['manual_description']=values.get('manual_description'),values.get('original_description')
    return values


def repair_company(company,actor):
    """Explicit maintenance operation under company/account locks; audited and retry-safe."""
    from .models import BankImportRow,BankMovement,BankEvent,Account,BankPosting,BankDecision
    from .bank_posting import movement_data,event,fingerprint,advance
    from django.db.models import Q
    from collections import Counter
    result=Counter();accounts=set()
    rows=BankImportRow.objects.filter(batch__account__company=company,migration_row__kind='debit',
        migration_row__batch__parser_version='dr-enriched-xlsx-v1').select_related('migration_row__batch','batch').defer('batch__original_file','migration_row__batch__original_file')
    for row in rows:
        raw=row.migration_row.parsed;correct=parsed_business_fields(row.migration_row)
        old_source=dict(row.parsed);old_assignments=dict(row.migration_assignments)
        if row.parsed.get('description')==(raw.get('original_description') or ''):
            row.parsed={**row.parsed,'description':correct.get('original_description') or ''}
        if row.migration_assignments.get('description')==(raw.get('manual_description') or ''):
            row.migration_assignments={**row.migration_assignments,'description':correct.get('manual_description') or ''}
        if row.parsed!=old_source or row.migration_assignments!=old_assignments:
            row.save(update_fields=['parsed','migration_assignments'])
            BankEvent.objects.create(row=row,actor=actor,action='description_interpretation',before={'source':old_source,'migration_assignments':old_assignments},
                after={'source':row.parsed,'migration_assignments':row.migration_assignments},note='Correct historical expense column interpretation; original workbook and cells retained.')
            result['preview_rows']+=1;accounts.add(row.batch.account_id)
        linked=BankDecision.objects.filter(row=row,posting__status__in=['active','partial_undo']).values('movement_id')
        for movement in BankMovement.objects.filter(Q(created_from=row)|Q(pk__in=linked),active=True,manual_key__isnull=True).select_related('classification','account').select_for_update(of=('self',)):
            # A previous maintenance event makes this upgrade idempotent, including
            # descriptions that happen to be equal or were edited afterwards.
            if movement.events.filter(action='description_interpretation').exists():continue
            before=movement_data(movement);changed=False
            if movement.source.get('description')==(raw.get('original_description') or ''):
                movement.source={**movement.source,'description':correct.get('original_description') or ''}
                movement.fingerprint=fingerprint(movement.source);changed=movement.source!=before['source']
            item=getattr(movement,'classification',None)
            edited_description=any(e.before.get('classification',{}).get('description')!=e.after.get('classification',{}).get('description')
                for e in movement.events.filter(action__in=['classify','manual_edit']))
            if item and not edited_description and item.description==(raw.get('manual_description') or ''):
                item.description=correct.get('manual_description') or ''
                if item.description!=before['classification'].get('description'):
                    item.save(update_fields=['description']);movement.classification=item;changed=True
            if changed:
                movement.revision+=1;movement.save(update_fields=['source','fingerprint','revision','updated_at'])
                event(BankPosting.objects.filter(batch=row.batch).first(),actor,'description_interpretation',movement,row,before,
                    'Correct historical expense column interpretation; amount, date, review and other classifications preserved.')
                result['movements']+=1;accounts.add(movement.account_id)
    for account in Account.objects.filter(pk__in=accounts).order_by('pk').select_for_update():advance(account)
    return dict(result)
