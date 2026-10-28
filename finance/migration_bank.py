"""Explicitly selected historical bank entries reuse the normal bank posting ledger."""
from decimal import Decimal
from .models import BankImportBatch, BankImportRow, BankMovement, BankMovementClassification, BankDecision, Category, Terminal
from .bank_readers import normalized
from .bank_identity import description_text, identity_fields
from .bank_classification import missing_fields, snapshot, effective_kind
from core_data.models import Studio


def bank_issue(row):
    if not row.bank_date or row.amount is None or not row.amount:
        return 'invalid_bank_facts'
    if row.kind=='credit' and normalized(str(row.parsed.get('payment_method') or '')) in ('efectivo','cash'):
        return 'cash_entry'
    return ''


def bank_source(row):
    raw=row.parsed
    return {'bank_date':row.bank_date.isoformat(),'amount':str(row.amount),'balance':raw.get('balance'),
        'currency':'DOP','direction':row.kind,'description':raw.get('original_description') or '',
        'short_description':'','reference':raw.get('reference') or '', 'serial':raw.get('serial') or ''}


def prepare(batch,account,actor,ids):
    rows=list(batch.rows.order_by('sheet','source_row'))
    chosen=set(ids)
    if len(chosen)!=len(ids) or not chosen or chosen-{row.pk for row in rows}:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'row_ids':'Choose distinct rows from this workbook.'})
    selected=[row for row in rows if row.pk in chosen]
    positions={index for index,row in enumerate(rows,1) if row.pk in chosen}
    if BankDecision.objects.filter(posting__status__in=['active','partial_undo'],row__batch__migration_batch__isnull=False,
            row__batch__file_hash=batch.file_hash,row__row_number__in=positions,movement__active=True,
            movement__account__company=account.company).exclude(movement__account=account).exists():
        from rest_framework.exceptions import ValidationError
        raise ValidationError('Some selected workbook rows are already imported to another bank account. Review the earlier import first.')
    if any(bank_issue(row) for row in selected):
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'row_ids':'Cash entries or invalid bank dates/amounts cannot be posted to a bank account.'})
    if batch.status!='preview' or batch.file_issues or account.company_id!=batch.company_id or account.currency!='DOP':
        from rest_framework.exceptions import ValidationError
        raise ValidationError('Use a readable Dominican workbook and a bank account in the same company.')
    credit=sum((row.amount for row in selected if row.kind=='credit'),Decimal(0))
    debit=-sum((row.amount for row in selected if row.kind=='debit'),Decimal(0))
    derived=BankImportBatch.objects.create(account=account,provider='popular',migration_batch=batch,
        file_name=batch.file_name,file_hash=batch.file_hash,byte_size=batch.byte_size,original_file=batch.original_file,
        encoding='xlsx',parser_version='historical-bank-v1',status='preview',summary={
            'valid_rows':len(selected),'invalid_rows':0,'currency':'DOP','credit_total':str(credit),
            'debit_total':str(debit),'net_total':str(credit-debit),'financial_records_created':0,
            'origin':'historical','bank_origin_confirmed':True,'confirmed_row_ids':sorted(chosen)})
    BankImportRow.objects.bulk_create([BankImportRow(batch=derived,migration_row=row,row_number=index,
        source_line=row.source_row,source_line_end=row.source_row,kind='data',parsed=bank_source(row),raw=row.raw,issues=[],
        migration_assignments=proposal(account,row))
        for index,row in enumerate(rows,1) if row.pk in chosen])
    return derived


def map_assignments(movement,row):
    """Keep workbook manual decisions; resolve only exact, unambiguous configured labels."""
    if not row.migration_row_id:return
    raw=row.migration_row.parsed;item=BankMovementClassification(movement=movement,movement_kind=effective_kind(row.migration_row.kind,None));company=movement.account.company
    item.description=raw.get('manual_description') or ''
    item.operation_date=row.migration_row.operation_date if row.migration_row.kind=='credit' else None
    item.expense_period=row.migration_row.expense_period if row.migration_row.kind=='debit' else None
    location=normalized(str(raw.get('location') or ''))
    if location in ('administracion','administration'):
        item.administration=True
    else:
        studios=[s for s in Studio.objects.filter(site_id=company.site_id) if normalized(s.name)==location and location]
        if len(studios)==1 and (not movement.account.studios.exists() or movement.account.studios.filter(pk=studios[0].pk).exists()):
            item.studio=studios[0]
    if row.migration_row.kind=='debit':
        parents=[c for c in Category.objects.filter(company=company,parent__isnull=True) if normalized(c.name)==normalized(str(raw.get('category') or ''))]
        if len(parents)==1:
            item.category=parents[0]
            children=[c for c in Category.objects.filter(parent=item.category) if normalized(c.name)==normalized(str(raw.get('subcategory') or ''))]
            if len(children)==1:item.subcategory=children[0]
    methods={'cierre':'card_terminal','recurrente':'recurring','recurrentes':'recurring','link':'payment_link',
        'transferencia':'transfer','efectivo':'cash','cash':'cash'}
    item.channel=methods.get(normalized(str(raw.get('payment_method') or '')),'')
    identifier=str(raw.get('terminal') or '').strip()
    terminal=Terminal.objects.filter(account=movement.account,identifier=identifier,active=True).first() if identifier else None
    if terminal and (not item.studio_id or item.studio_id==terminal.studio_id) and (not item.channel or item.channel==terminal.channel) and not item.administration:
        item.terminal=terminal;item.studio_id=terminal.studio_id;item.channel=terminal.channel
    # A legacy checkbox is recognition only, and cannot certify incomplete mappings.
    values={'movement_kind':item.movement_kind,'studio':item.studio_id,'administration':item.administration,
        'category':item.category_id,'subcategory':item.subcategory_id,'expense_period':item.expense_period,
        'channel':item.channel,'operation_date':item.operation_date}
    item.reviewed=bool(raw.get('legacy_reviewed') is True and not missing_fields(row.migration_row.kind,values,
        bool(item.category_id and item.category.children.filter(active=True).exists())))
    movement.classification=item
    return snapshot(movement)


def compatible_historical(movement,source,incoming_historical=False):
    """A later bank report may add missing bank metadata, but must not conflict."""
    if not incoming_historical and (not movement.created_from_id or not movement.created_from.batch.migration_batch_id):return False
    old=movement.source
    if any(old.get(key)!=source.get(key) for key in ('bank_date','amount','currency','direction')):return False
    if old.get('description') and source.get('description') and description_text(old['description'])!=description_text(source['description']):return False
    if any(old.get(key) not in (None,'') and source.get(key) not in (None,'') and old[key]!=source[key] for key in ('reference','serial','balance')):return False
    return any(old.get(key) not in (None,'') and old.get(key)==source.get(key)
               for key in ('balance',*identity_fields(source,'popular')))


def proposal(account,origin):
    movement=BankMovement(account=account,source=bank_source(origin))
    row=BankImportRow(migration_row=origin)
    return map_assignments(movement,row)


def assignment_conflicts(movement,row):
    if not row.migration_row_id:return []
    before=snapshot(movement);values=row.migration_assignments
    conflicts=[key for key,value in values.items() if key!='reviewed' and value not in (None,'',False)
        and before.get(key)!=value and (before.get(key) not in (None,'',False) or movement.revision>1 or movement.reconciled or before.get('reviewed'))]
    if values.get('administration') and before.get('studio'):conflicts.append('studio')
    if values.get('studio') and before.get('administration'):conflicts.append('administration')
    return sorted(set(conflicts))


def apply_assignments(movement,row,fill=False):
    if not row.migration_row_id:return False
    if fill and (movement.reconciled or assignment_conflicts(movement,row)):return False
    from datetime import date
    values=row.migration_assignments
    from rest_framework.exceptions import ValidationError
    studio_id=values.get('studio');category_id=values.get('category');subcategory_id=values.get('subcategory')
    if studio_id and (not Studio.objects.filter(pk=studio_id,site_id=movement.account.company.site_id).exists() or
            (movement.account.studios.exists() and not movement.account.studios.filter(pk=studio_id).exists())):
        raise ValidationError('Studio configuration changed. Prepare a fresh historical import.')
    if category_id and not Category.objects.filter(pk=category_id,company=movement.account.company,parent__isnull=True).exists():
        raise ValidationError('Category configuration changed. Prepare a fresh historical import.')
    if subcategory_id and not Category.objects.filter(pk=subcategory_id,company=movement.account.company,parent_id=category_id).exists():
        raise ValidationError('Subcategory configuration changed. Prepare a fresh historical import.')
    if values.get('terminal') and not Terminal.objects.filter(pk=values['terminal'],account=movement.account,active=True,
            studio_id=studio_id,channel=values.get('channel')).exists():
        raise ValidationError('Terminal configuration changed. Prepare a fresh historical import.')
    item,_=BankMovementClassification.objects.get_or_create(movement=movement,defaults={'movement_kind':effective_kind(movement.source['direction'],None)})
    movement.classification=item;before=snapshot(movement)
    for key,value in values.items():
        if fill and (value in (None,'',False) or before.get(key) not in (None,'',False)):continue
        if key in ('operation_date','expense_period') and value:value=date.fromisoformat(value)
        setattr(item,key+'_id' if key in ('category','subcategory','studio','terminal') else key,value)
    # Current completion rules still apply if configuration changed since preparation.
    candidate=snapshot(movement)
    if missing_fields(movement.source['direction'],candidate,bool(item.category_id and item.category.children.filter(active=True).exists())):
        item.reviewed=False
    item.save();movement.classification=item
    return snapshot(movement)!=before
