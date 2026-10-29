"""Financial posting operations. All callers hold company then account locks."""
import hashlib
import json
from collections import Counter, defaultdict
from django.utils import timezone
from rest_framework import serializers
from .configuration import ConfigurationConflict
from .bank_identity import comparable_source, transaction_facts, identity_fields
from .bank_classification import recognize_terminal, terminal_patterns, initialize_classification
from .models import BankDecision, BankEvent, BankMovement, BankPosting


def fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def movement_data(movement):
    from .bank_classification import snapshot
    return {'id': movement.pk, 'account':movement.account_id, 'revision': movement.revision, 'active': movement.active,
            'reconciled': movement.reconciled, 'source': movement.source, 'classification': snapshot(movement)}


def token(account, batch, purpose='commit', revision=0):
    origin_state=[]
    if batch.migration_batch_id:
        origin_state=list(BankDecision.objects.filter(posting__status__in=['active','partial_undo'],
            row__batch__migration_batch__isnull=False,row__batch__file_hash=batch.file_hash,
            movement__account__company_id=account.company_id,movement__active=True).order_by('pk').values_list('pk','movement_id','movement__revision','posting__revision'))
    return hashlib.sha256(f'bank-plan-v4:{account.pk}:{account.ledger_revision}:{batch.pk}:{purpose}:{revision}:{origin_state}'.encode()).hexdigest()


def advance(account):
    account.ledger_revision += 1
    account.save(update_fields=['ledger_revision'])


def event(posting, actor, action, movement=None, row=None, before=None, note=''):
    return BankEvent.objects.create(posting=posting, actor=actor, action=action, movement=movement,
        row=row, before=before or {}, after=movement_data(movement) if movement else {}, note=note)


def plan(batch, account):
    rows = list(batch.rows.filter(kind='data').select_related('migration_row'))
    from django.db.models import Q
    movements = list(BankMovement.objects.filter(Q(provider=batch.provider)|Q(provider='manual',manual_key__isnull=False),account=account,active=True).select_related('classification','created_from__batch'))
    normalized_exact = defaultdict(list); identifiers = defaultdict(set); balances = defaultdict(set); weak = defaultdict(set); day_description = defaultdict(set); balance_description = defaultdict(set)
    historical=defaultdict(set); facts=defaultdict(set)
    by_id = {m.pk: m for m in movements}
    for m in movements:
        data = m.source
        normalized_exact[fingerprint(comparable_source(data))].append(m.pk)
        facts[transaction_facts(data)].add(m.pk)
        if not m.created_from_id or m.created_from.batch.migration_batch_id:historical[(data['bank_date'],data['amount'])].add(m.pk)
        for key in identity_fields(data,batch.provider):
            if data.get(key): identifiers[(key, data[key])].add(m.pk)
        if data.get('balance') is not None:
            balances[(data['bank_date'], data['balance'])].add(m.pk)
            balance_description[(data['balance'], data['description'])].add(m.pk)
        weak[(data['bank_date'], data['amount'], data['description'])].add(m.pk)
        day_description[(data['bank_date'], data['description'])].add(m.pk)
    # Linked raw reports may supply IDs absent in the original workbook. Retain
    # those identities as evidence without rewriting the historical primary source.
    linked=BankDecision.objects.filter(posting__status__in=['active','partial_undo'],movement_id__in=by_id).select_related('row')
    for decision in linked:
        original=by_id[decision.movement_id]
        if original.created_from_id and not original.created_from.batch.migration_batch_id:continue
        for key in identity_fields(decision.row.parsed,batch.provider):
            value=decision.row.parsed.get(key)
            if value:identifiers[(key,value)].add(decision.movement_id)
    counts = Counter(fingerprint(comparable_source(r.parsed)) for r in rows if not r.issues)
    fact_counts = Counter((transaction_facts(r.parsed),r.parsed.get('balance')) for r in rows if not r.issues)
    prior = defaultdict(set);prior_sources=defaultdict(list)
    evidence = BankDecision.objects.filter(posting__status__in=['active', 'partial_undo'], row__batch__account=account,
        row__batch__provider=batch.provider, row__batch__file_hash=batch.file_hash,
        movement__active=True).exclude(row__batch=batch).select_related('row')
    for decision in evidence:
        prior[decision.row.row_number].add(decision.movement_id)
        prior_sources[decision.row.row_number].append(decision.row.parsed)
    posting = BankPosting.objects.filter(batch=batch).first()
    decisions = {d.row_id: d for d in posting.decisions.all()} if posting else {}
    elsewhere=set()
    if batch.migration_batch_id:
        elsewhere=set(BankDecision.objects.filter(posting__status__in=['active','partial_undo'],
            row__batch__migration_batch__isnull=False,row__batch__file_hash=batch.file_hash,
            movement__account__company_id=account.company_id,movement__active=True).exclude(movement__account=account).values_list('row__row_number',flat=True))
    result = []
    for row in rows:
        data = row.parsed; ids = set(); outcome = 'invalid'; target = None
        if not row.issues:
            fp = fingerprint(comparable_source(data))
            same = [pk for pk in normalized_exact[fp] if comparable_source(by_id[pk].source) == comparable_source(data)]
            known = prior[row.row_number]
            if known:
                ids = known
                if len(known) == 1 and (comparable_source(by_id[next(iter(known))].source) == comparable_source(data) or by_id[next(iter(known))].manual_key and data in prior_sources[row.row_number]):
                    outcome = 'unchanged'; target = next(iter(known))
                else:
                    outcome = 'correction' if len(known) == 1 else 'ambiguous'
            elif len(same) == 1 and counts[fp] == 1 and any(data.get(key) is not None and data.get(key) != '' for key in ('balance',*identity_fields(data,batch.provider))):
                outcome = 'unchanged'; target = same[0]; ids = set(same)
            elif same:
                outcome = 'ambiguous'; ids = set(same)
            else:
                ids |= known
                ids |= historical[(data['bank_date'],data['amount'])]
                ids |= {pk for pk in facts[transaction_facts(data)] if data.get('balance') is None or
                        by_id[pk].source.get('balance') is None or by_id[pk].source.get('balance')==data['balance']}
                for key in identity_fields(data,batch.provider):
                    if data.get(key): ids |= identifiers[(key, data[key])]
                if data.get('balance') is not None:
                    ids |= balances[(data['bank_date'], data['balance'])]
                    ids |= balance_description[(data['balance'], data['description'])]
                if not identity_fields(data,batch.provider) or not any(data.get(k) for k in identity_fields(data,batch.provider)):
                    ids |= {pk for pk in day_description[(data['bank_date'], data['description'])]
                            if data.get('balance') is None or by_id[pk].source.get('balance') is None or by_id[pk].source.get('balance')==data['balance']}
                # Missing balance cannot distinguish otherwise equal bank occurrences.
                ids |= {pk for pk in weak[(data['bank_date'], data['amount'], data['description'])]
                        if data.get('balance') is None or by_id[pk].source.get('balance') is None}
                ids = {pk for pk in ids if by_id[pk].source.get('currency')==data.get('currency') and
                       by_id[pk].source.get('direction')==data.get('direction') and not (
                           transaction_facts(by_id[pk].source)==transaction_facts(data) and
                           data.get('balance') is not None and by_id[pk].source.get('balance') is not None and
                           by_id[pk].source['balance']!=data['balance'])}
                outcome = 'correction' if len(ids) == 1 else 'ambiguous' if ids else 'new'
                # Added or missing metadata may support the same four bank facts;
                # conflicting nonempty reference/serial values still require review.
                exact_facts=[pk for pk in ids if transaction_facts(by_id[pk].source)==transaction_facts(data) and
                             data.get('balance') is not None and by_id[pk].source.get('balance')==data['balance'] and
                             not any(by_id[pk].source.get(k) not in (None,'') and data.get(k) not in (None,'') and
                                     by_id[pk].source[k]!=data[k] for k in ('reference','serial'))]
                if len(exact_facts)==1 and fact_counts[(transaction_facts(data),data.get('balance'))]==1:
                    outcome='unchanged';target=exact_facts[0];ids={target}
                elif exact_facts and fact_counts[(transaction_facts(data),data.get('balance'))]>1:
                    outcome='ambiguous'
        # A reused AZUL terminal/serial is weak evidence across days. Prefer a
        # unique compatible same-day amount/balance identity, without discarding
        # substantive description or identifier conflicts.
        if outcome in ('correction','ambiguous') and data.get('balance') is not None and counts.get(fingerprint(comparable_source(data)))==1:
            from .migration_bank import compatible_historical
            strong=[pk for pk in ids if by_id[pk].source.get('balance')==data['balance'] and
                compatible_historical(by_id[pk],data,incoming_historical=bool(row.migration_row_id))]
            if len(strong)==1:outcome='unchanged';target=strong[0];ids={target}
        if outcome=='correction' and len(ids)==1 and counts.get(fingerprint(comparable_source(data)))==1:
            from .migration_bank import compatible_historical
            candidate=by_id[next(iter(ids))]
            if compatible_historical(candidate,data,incoming_historical=bool(row.migration_row_id)):
                outcome='unchanged';target=candidate.pk
        if row.migration_row_id and row.row_number in elsewhere:
            outcome='origin_conflict';target=None;ids=set()
        conflicts=[]
        if outcome=='unchanged' and row.migration_row_id:
            from .migration_bank import assignment_conflicts
            conflicts=assignment_conflicts(by_id[target],row)
            if conflicts:outcome='assignment_conflict'
        decision = decisions.get(row.pk)
        if outcome=='unchanged' and any(d.movement_id==target and d.row_id!=row.pk for d in decisions.values()):
            outcome='ambiguous';target=None
        item = {'row_id': row.pk, 'source_line': row.source_line, 'source': data, 'issues': row.issues,
                'outcome': outcome, 'target': target, 'candidate_count': len(ids),
                'candidates': [movement_data(by_id[pk]) for pk in sorted(ids,key=lambda pk:(
                    any(by_id[pk].source.get(k)!=data.get(k) for k in ('bank_date','amount','currency','direction')),
                    data.get('balance') is None or by_id[pk].source.get('balance')!=data.get('balance'),pk))[:50]],
                'assignment_conflicts':conflicts,'migration_source':row.migration_row.parsed if row.migration_row_id else None,
                'migration_sheet':row.migration_row.sheet if row.migration_row_id else None}
        if decision:
            item.update(decision_id=decision.pk, revision=decision.revision, resolution=decision.resolution,
                        movement_id=decision.movement_id)
            if decision.resolution != 'pending': item['outcome'] = decision.resolution
        result.append(item)
    claimed=Counter(item['target'] for item in result if item['outcome']=='unchanged')
    for item in result:
        if item['outcome']=='unchanged' and claimed[item['target']]>1:
            item['outcome']='ambiguous';item['target']=None
    return {'token': token(account, batch), 'counts': dict(Counter(r['outcome'] for r in result)),
            'rows': result, 'posting': posting}


def apply_pending(batch, account, actor, expected):
    """Apply only freshly unambiguous pending rows; retain all previous decisions."""
    current=plan(batch,account)
    if current['token']!=expected:raise ConfigurationConflict('The ledger changed. Refresh the pending review.')
    posting=current['posting']
    if not posting or posting.status!='active':raise ConfigurationConflict('Choose an active imported report.')
    changed=Counter()
    for item in current['rows']:
        if item.get('resolution')!='pending' or item['outcome'] not in ('new','unchanged'):continue
        decision=posting.decisions.select_related('posting__batch','row').get(pk=item['decision_id'])
        target=BankMovement.objects.get(pk=item['target']) if item['outcome']=='unchanged' else None
        action='link' if target else 'create'
        resolve(decision,account,actor,action,item['revision'],
                'Applied refreshed date, amount, description and balance matching',target,target.revision if target else None)
        changed[action]+=1
    return dict(changed)


def commit(batch, account, actor, expected):
    existing = BankPosting.objects.filter(batch=batch).first()
    if existing:
        if existing.status != 'active': raise ConfigurationConflict('This import was undone. Upload a new preview to import again.')
        return existing
    if batch.status != 'preview' or not batch.summary.get('valid_rows'):
        raise serializers.ValidationError('Only a successful preview with valid bank rows can be imported.')
    current = plan(batch, account)
    if current['token'] != expected: raise ConfigurationConflict('The account ledger changed. Reload the import plan.')
    posting = BankPosting.objects.create(batch=batch, actor=actor)
    patterns=terminal_patterns(account,actor)
    used = set()
    rows = {r.pk: r for r in batch.rows.filter(kind='data').select_related('migration_row')}
    for item in current['rows']:
        row = rows[item['row_id']]
        decision = BankDecision(posting=posting, row=row, outcome=item['outcome'])
        if item['outcome'] == 'new':
            movement = BankMovement.objects.create(account=account, provider=batch.provider, source=row.parsed,
                fingerprint=fingerprint(row.parsed), created_from=row)
            initialize_classification(movement)
            from .migration_bank import apply_assignments
            apply_assignments(movement,row)
            recognize_terminal(movement,actor,patterns=patterns)
            decision.movement = movement; decision.resolution = 'created'
            event(posting, actor, 'create', movement, row)
        elif item['outcome'] == 'unchanged' and item['target'] not in used:
            decision.movement_id = item['target']; decision.resolution = 'linked'
            movement=BankMovement.objects.get(pk=item['target'])
            from .migration_bank import apply_assignments
            before=movement_data(movement)
            if apply_assignments(movement,row,fill=True):
                movement.revision+=1;movement.save(update_fields=['revision','updated_at'])
                event(posting,actor,'classify',movement,row,before,note='Historical workbook assignments filled missing fields')
            event(posting, actor, 'link', movement, row)
        elif item['outcome'] in ('invalid','origin_conflict'):
            decision.resolution = item['outcome']
        if decision.movement_id: used.add(decision.movement_id)
        decision.save()
    event(posting, actor, 'commit')
    advance(account)
    return posting


def resolve(decision, account, actor, action, expected_revision, note, target=None, target_revision=None):
    posting = decision.posting
    if posting.status != 'active': raise ConfigurationConflict('This import is no longer active.')
    if decision.revision != expected_revision or decision.resolution != 'pending':
        raise ConfigurationConflict('This row was already resolved. Reload the review.')
    if decision.row.issues: raise serializers.ValidationError('Upload a corrected source file for invalid rows.')
    if decision.outcome=='assignment_conflict' and action in ('create','correct'):
        raise serializers.ValidationError('Link or ignore this already identified movement; edit business assignments in Records.')
    if action in ('link', 'correct'):
        if not target or target.account_id != account.pk or target.provider not in (posting.batch.provider,'manual') or not target.active:
            raise serializers.ValidationError('Choose an active movement from this account and bank format.')
        if target.revision != target_revision: raise ConfigurationConflict('The movement changed. Reload before resolving.')
        if posting.decisions.filter(movement=target).exists():
            raise serializers.ValidationError('Another row in this import already uses that movement. Keep distinct occurrences separate.')
        before = movement_data(target)
        if action == 'correct':
            if target.manual_key:raise serializers.ValidationError('Link bank evidence to a manual entry; do not overwrite its independent facts.')
            if decision.outcome=='assignment_conflict':raise serializers.ValidationError('Edit assignments in Records, or link to retain existing decisions. Source correction does not resolve assignment conflicts.')
            from .review_workflow import assert_bank_editable
            assert_bank_editable(target)
            if target.reconciled: raise serializers.ValidationError('Reconciled movements require reconciliation review before source correction.')
            target.source = decision.row.parsed; target.fingerprint = fingerprint(target.source)
            target.revision += 1; target.save()
        if action=='link' and decision.row.migration_row_id:
            from .migration_bank import apply_assignments
            if apply_assignments(target,decision.row,fill=True):
                target.revision+=1;target.save(update_fields=['revision','updated_at'])
                event(posting,actor,'classify',target,decision.row,before,note='Historical assignments filled after explicit identity review')
        decision.movement = target; decision.resolution = 'corrected' if action == 'correct' else 'linked'
        event(posting, actor, action, target, decision.row, before, note)
    elif action == 'create':
        movement = BankMovement.objects.create(account=account, provider=posting.batch.provider,
            source=decision.row.parsed, fingerprint=fingerprint(decision.row.parsed), created_from=decision.row)
        initialize_classification(movement)
        from .migration_bank import apply_assignments
        apply_assignments(movement,decision.row)
        recognize_terminal(movement,actor)
        decision.movement = movement; decision.resolution = 'created'
        event(posting, actor, 'create', movement, decision.row, note=note)
    elif action == 'ignore':
        decision.resolution = 'ignored'; event(posting, actor, 'ignore', row=decision.row, note=note)
    else:
        raise serializers.ValidationError('Choose a supported resolution.')
    decision.revision += 1; decision.save()
    posting.revision += 1; posting.save(update_fields=['revision'])
    advance(account)


def undo_plan(posting, account):
    from .review_workflow import bank_locked
    eligible = []; protected = []; reused = 0
    for decision in posting.decisions.select_related('movement').all():
        movement = decision.movement
        if decision.resolution == 'corrected':
            protected.append({'movement_id': movement.pk, 'reason': 'source_correction'})
        elif decision.resolution != 'created':
            if movement: reused += 1
        elif movement.active:
            reason = None
            if bank_locked(movement): reason = 'reviewed'
            elif movement.reconciled: reason = 'reconciled'
            elif movement.revision != 1: reason = 'changed'
            elif movement.decisions.filter(posting__status__in=['active', 'partial_undo']).exclude(posting=posting).exists(): reason = 'other_import'
            if reason: protected.append({'movement_id': movement.pk, 'reason': reason})
            else: eligible.append(movement.pk)
    return {'token': token(account, posting.batch, 'undo', posting.revision),
            'eligible': eligible, 'protected': protected, 'reused_unchanged': reused}


def undo(posting, account, actor, expected, note):
    prior = posting.events.filter(action='undo_import', after__request_token=expected).first()
    if prior:
        return prior.after['result']
    if posting.status == 'undone': return undo_plan(posting, account)
    current = undo_plan(posting, account)
    if current['token'] != expected: raise ConfigurationConflict('Undo eligibility changed. Reload the undo preview.')
    if posting.status == 'partial_undo' and not current['eligible']:
        return current
    for movement in BankMovement.objects.filter(pk__in=current['eligible']):
        before = movement_data(movement)
        movement.active = False; movement.revision += 1; movement.save()
        event(posting, actor, 'undo_movement', movement, before=before, note=note)
    posting.status = 'partial_undo' if current['protected'] else 'undone'
    posting.undone_at = timezone.now(); posting.revision += 1; posting.save()
    audit = event(posting, actor, 'undo_import', note=note)
    audit.after = {'request_token': expected, 'result': current}
    audit.save(update_fields=['after'])
    advance(account)
    return current
