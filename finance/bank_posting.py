"""Financial posting operations. All callers hold company then account locks."""
import hashlib
import json
from collections import Counter, defaultdict
from django.utils import timezone
from rest_framework import serializers
from .configuration import ConfigurationConflict
from .bank_classification import recognize_terminal, terminal_patterns
from .models import BankDecision, BankEvent, BankMovement, BankPosting


def fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def movement_data(movement):
    from .bank_classification import snapshot
    return {'id': movement.pk, 'revision': movement.revision, 'active': movement.active,
            'reconciled': movement.reconciled, 'source': movement.source, 'classification': snapshot(movement)}


def token(account, batch, purpose='commit', revision=0):
    return hashlib.sha256(f'bank-plan-v1:{account.pk}:{account.ledger_revision}:{batch.pk}:{purpose}:{revision}'.encode()).hexdigest()


def advance(account):
    account.ledger_revision += 1
    account.save(update_fields=['ledger_revision'])


def event(posting, actor, action, movement=None, row=None, before=None, note=''):
    return BankEvent.objects.create(posting=posting, actor=actor, action=action, movement=movement,
        row=row, before=before or {}, after=movement_data(movement) if movement else {}, note=note)


def plan(batch, account):
    rows = list(batch.rows.filter(kind='data'))
    movements = list(BankMovement.objects.filter(account=account, provider=batch.provider, active=True).select_related('classification'))
    exact = defaultdict(list); identifiers = defaultdict(set); balances = defaultdict(set); weak = defaultdict(set); day_description = defaultdict(set); balance_description = defaultdict(set)
    by_id = {m.pk: m for m in movements}
    for m in movements:
        data = m.source
        exact[m.fingerprint].append(m.pk)
        for key in ('reference', 'serial'):
            if data.get(key): identifiers[(key, data[key])].add(m.pk)
        if data.get('balance') is not None:
            balances[(data['bank_date'], data['balance'])].add(m.pk)
            balance_description[(data['balance'], data['description'])].add(m.pk)
        weak[(data['bank_date'], data['amount'], data['description'])].add(m.pk)
        day_description[(data['bank_date'], data['description'])].add(m.pk)
    counts = Counter(fingerprint(r.parsed) for r in rows if not r.issues)
    prior = defaultdict(set)
    evidence = BankDecision.objects.filter(posting__status__in=['active', 'partial_undo'], row__batch__account=account,
        row__batch__provider=batch.provider, row__batch__file_hash=batch.file_hash,
        movement__active=True).exclude(row__batch=batch).select_related('row')
    for decision in evidence:
        prior[decision.row.row_number].add(decision.movement_id)
    posting = BankPosting.objects.filter(batch=batch).first()
    decisions = {d.row_id: d for d in posting.decisions.all()} if posting else {}
    result = []
    for row in rows:
        data = row.parsed; ids = set(); outcome = 'invalid'; target = None
        if not row.issues:
            fp = fingerprint(data)
            same = [pk for pk in exact[fp] if by_id[pk].source == data]
            known = prior[row.row_number]
            if known:
                ids = known
                if len(known) == 1 and by_id[next(iter(known))].source == data:
                    outcome = 'unchanged'; target = next(iter(known))
                else:
                    outcome = 'correction' if len(known) == 1 else 'ambiguous'
            elif len(same) == 1 and counts[fp] == 1 and any(data.get(key) is not None and data.get(key) != '' for key in ('balance','reference','serial')):
                outcome = 'unchanged'; target = same[0]; ids = set(same)
            elif same:
                outcome = 'ambiguous'; ids = set(same)
            else:
                ids |= known
                for key in ('reference', 'serial'):
                    if data.get(key): ids |= identifiers[(key, data[key])]
                if data.get('balance') is not None:
                    ids |= balances[(data['bank_date'], data['balance'])]
                    ids |= balance_description[(data['balance'], data['description'])]
                if not data.get('reference') and not data.get('serial'):
                    ids |= day_description[(data['bank_date'], data['description'])]
                # Missing balance cannot distinguish otherwise equal bank occurrences.
                ids |= {pk for pk in weak[(data['bank_date'], data['amount'], data['description'])]
                        if data.get('balance') is None or by_id[pk].source.get('balance') is None}
                outcome = 'correction' if len(ids) == 1 else 'ambiguous' if ids else 'new'
        decision = decisions.get(row.pk)
        item = {'row_id': row.pk, 'source_line': row.source_line, 'source': data, 'issues': row.issues,
                'outcome': outcome, 'target': target, 'candidate_count': len(ids),
                'candidates': [movement_data(by_id[pk]) for pk in sorted(ids)[:50]]}
        if decision:
            item.update(decision_id=decision.pk, revision=decision.revision, resolution=decision.resolution,
                        movement_id=decision.movement_id)
            if decision.resolution != 'pending': item['outcome'] = decision.resolution
        result.append(item)
    return {'token': token(account, batch), 'counts': dict(Counter(r['outcome'] for r in result)),
            'rows': result, 'posting': posting}


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
    rows = {r.pk: r for r in batch.rows.filter(kind='data')}
    for item in current['rows']:
        row = rows[item['row_id']]
        decision = BankDecision(posting=posting, row=row, outcome=item['outcome'])
        if item['outcome'] == 'new':
            movement = BankMovement.objects.create(account=account, provider=batch.provider, source=row.parsed,
                fingerprint=fingerprint(row.parsed), created_from=row)
            recognize_terminal(movement,actor,patterns=patterns)
            decision.movement = movement; decision.resolution = 'created'
            event(posting, actor, 'create', movement, row)
        elif item['outcome'] == 'unchanged' and item['target'] not in used:
            decision.movement_id = item['target']; decision.resolution = 'linked'
            event(posting, actor, 'link', BankMovement.objects.get(pk=item['target']), row)
        elif item['outcome'] == 'invalid':
            decision.resolution = 'invalid'
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
    if action in ('link', 'correct'):
        if not target or target.account_id != account.pk or target.provider != posting.batch.provider or not target.active:
            raise serializers.ValidationError('Choose an active movement from this account and bank format.')
        if target.revision != target_revision: raise ConfigurationConflict('The movement changed. Reload before resolving.')
        if posting.decisions.filter(movement=target).exists():
            raise serializers.ValidationError('Another row in this import already uses that movement. Keep distinct occurrences separate.')
        before = movement_data(target)
        if action == 'correct':
            if target.reconciled: raise serializers.ValidationError('Reconciled movements require reconciliation review before source correction.')
            target.source = decision.row.parsed; target.fingerprint = fingerprint(target.source)
            target.revision += 1; target.save()
        decision.movement = target; decision.resolution = 'corrected' if action == 'correct' else 'linked'
        event(posting, actor, action, target, decision.row, before, note)
    elif action == 'create':
        movement = BankMovement.objects.create(account=account, provider=posting.batch.provider,
            source=decision.row.parsed, fingerprint=fingerprint(decision.row.parsed), created_from=decision.row)
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
    eligible = []; protected = []; reused = 0
    for decision in posting.decisions.select_related('movement').all():
        movement = decision.movement
        if decision.resolution == 'corrected':
            protected.append({'movement_id': movement.pk, 'reason': 'source_correction'})
        elif decision.resolution != 'created':
            if movement: reused += 1
        elif movement.active:
            reason = None
            if movement.reconciled: reason = 'reconciled'
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
