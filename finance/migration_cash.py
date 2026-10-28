"""Explicit actual-cash workbook receipts. No inference from invoices or bank totals."""
from .models import BankMovement, BankImportRow
from .migration_bank import bank_issue,bank_source,proposal,apply_assignments
from .bank_posting import fingerprint,event,advance
from decimal import Decimal


def source_key(batch,row):
    return fingerprint([batch.company_id,batch.file_hash,row.sheet,row.source_row,'cash'])


def cash_plan(batch,account):
    rows=[];participating=set(account.studios.values_list('pk',flat=True))
    existing=list(BankMovement.objects.filter(account__company_id=batch.company_id).select_related('historical_row__batch','account'))
    indexed={m.source_key:m for m in existing if m.source_key}
    for row in batch.rows.all():
        if str(row.parsed.get('payment_method') or '').strip().casefold() not in ('cash','efectivo'):continue
        if row.kind!='credit':continue # Historical debit origin is the selected bank by client decision.
        key=source_key(batch,row);match=indexed.get(key);candidates=[]
        if match:status='already_imported' if match.active else 'previously_voided'
        elif bank_issue(row)=='invalid_bank_facts':status='invalid'
        elif participating and proposal(account,row).get('studio') not in participating:status='account_scope_review'
        else:
            source=bank_source(row)
            for movement in existing:
                if not movement.active or movement.account.kind!='cash':continue
                if movement.historical_row_id and movement.historical_row.batch.file_hash==batch.file_hash:continue
                if all(movement.source.get(k)==source.get(k) for k in ('bank_date','amount','currency','direction')):candidates.append(movement.pk)
            status='possible_overlap' if candidates else 'new'
        rows.append({'row_id':row.pk,'sheet':row.sheet,'source_row':row.source_row,'date':row.bank_date,
            'amount':f'{row.amount:.2f}' if row.amount is not None else None,'description':row.parsed.get('manual_description'),'studio':row.parsed.get('location'),
            'status':status,'existing_id':match.pk if match else None,'existing_account_name':match.account.name if match else None,'candidates':candidates,'source_key':key})
    token=fingerprint(['cash-migration-v1',batch.pk,account.pk,account.ledger_revision,
        [(m.pk,m.revision,m.active) for m in existing],[(r['row_id'],r['status']) for r in rows]])
    return {'token':token,'rows':rows,'new':sum(r['status']=='new' for r in rows),
        'new_total':f"{sum((Decimal(r['amount']) for r in rows if r['status']=='new'),Decimal(0)):.2f}",
        'already_imported':sum(r['status']=='already_imported' for r in rows),
        'pending':sum(r['status'] in ('invalid','possible_overlap','previously_voided','account_scope_review') for r in rows),
        'balance_verified':False}


def import_cash(batch,account,actor,expected):
    from .configuration import ConfigurationConflict
    current=cash_plan(batch,account)
    if expected!=current['token']:raise ConfigurationConflict('Cash records changed. Review a fresh preview.')
    lookup={r.pk:r for r in batch.rows.all()};created=[]
    for item in current['rows']:
        if item['status']!='new':continue
        row=lookup[item['row_id']];source=bank_source(row);source['balance']=None
        movement=BankMovement.objects.create(account=account,provider='cash',source=source,fingerprint=fingerprint(source),
            historical_row=row,source_key=item['source_key'],manual_actor=actor)
        bridge=BankImportRow(migration_row=row,migration_assignments=proposal(account,row))
        apply_assignments(movement,bridge)
        event(None,actor,'cash_migration',movement,note='Historical workbook actual cash receipt')
        created.append(movement.pk)
    if created:advance(account)
    return {'created':len(created),'already_imported':current['already_imported'],'pending':current['pending']}


def recovery_plan(batch,account,actor,mode):
    """Undo/restore only unchanged own imports, never silently erase subsequent work."""
    from .access import can_use_finance
    from .bank_posting import movement_data
    from .models import ClosureCheck
    items=list(BankMovement.objects.filter(account=account,historical_row__batch__company=batch.company,
        historical_row__batch__file_hash=batch.file_hash,provider='cash').select_related('classification','historical_row__batch'))
    active_cash=list(BankMovement.objects.filter(account__company=batch.company,account__kind='cash',active=True).select_related('historical_row__batch'))
    checked=set()
    for check in ClosureCheck.objects.filter(company=batch.company,state='checked'):
        checked.update(r['id'] for r in check.snapshot.get('records',[]) if r.get('side')=='actual')
    can_write=can_use_finance(actor,'can_import_finance') and can_use_finance(actor,'can_edit_finance')
    manager=can_use_finance(actor,'can_manage_finance_settings')
    eligible=[];protected=[];states=[]
    for item in items:
        if item.active!=(mode=='undo'):continue
        latest=item.events.order_by('-pk').first();reason=None
        if not can_write or (item.manual_actor_id!=actor.pk and not manager):reason='permission'
        elif item.reconciled or item.pk in checked:reason='checked'
        elif not latest or latest.action not in (('cash_migration','cash_migration_restore') if mode=='undo' else ('cash_migration_undo',)):reason='changed'
        elif latest.after!=movement_data(item):reason='changed'
        elif item.decisions.filter(posting__status__in=['active','partial_undo']).exists():reason='linked'
        elif mode=='restore':
            c=getattr(item,'classification',None);studios=set(account.studios.values_list('pk',flat=True))
            if studios and (not c or c.studio_id not in studios):reason='account_scope'
            for candidate in active_cash:
                if candidate.historical_row_id and candidate.historical_row.batch.file_hash==batch.file_hash:continue
                if all(candidate.source.get(k)==item.source.get(k) for k in ('bank_date','amount','currency','direction')):reason='possible_overlap';break
        states.append(movement_data(item))
        if reason:protected.append({'id':item.pk,'reason':reason})
        else:eligible.append(item.pk)
    token=fingerprint(['cash-recovery-v1',batch.company_id,batch.pk,account.pk,mode,account.ledger_revision,
        states,[(m.pk,m.revision,m.active) for m in active_cash],eligible,protected])
    return {'token':token,'eligible':eligible,'protected':protected,'mode':mode,'can_write':bool(can_write)}


def recover_cash(batch,account,actor,mode,expected,note):
    from .configuration import ConfigurationConflict
    from .bank_posting import movement_data
    current=recovery_plan(batch,account,actor,mode)
    if expected!=current['token']:raise ConfigurationConflict('Cash records changed. Review a fresh recovery preview.')
    if not current['can_write']:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied()
    for item in BankMovement.objects.select_for_update().filter(pk__in=current['eligible']):
        before=movement_data(item);item.active=mode=='restore';item.revision+=1;item.save(update_fields=['active','revision','updated_at'])
        event(None,actor,'cash_migration_'+mode,item,before=before,note=note)
    if current['eligible']:advance(account)
    return {'changed':len(current['eligible']),'protected':len(current['protected']),'mode':mode}
