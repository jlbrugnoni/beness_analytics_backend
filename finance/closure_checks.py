"""Operational checks preserve evidence, without mutating source reconciled flags."""
from decimal import Decimal
from django.utils import timezone
from .bank_posting import fingerprint
from .models import ClosureCheck,ClosureCheckEvent,FeePolicy
from .configuration import ConfigurationConflict
from rest_framework.exceptions import ValidationError


def snapshot(summary,rows,channel,day,policies):
    group=next(m for m in summary['methods'] if m['channel']==channel)
    totals=next(d for d in group['days'] if d['date']==day)
    # Running totals belong to other days; they cannot invalidate this day's check.
    values={k:v for k,v in totals.items() if not k.startswith('cumulative_') and k not in ('check','check_token')}
    records=[{k:r.get(k) for k in ('side','id','revision','source_hash','sale_revision','amount','studio','issues','included','excluded_kind')}
        for r in rows if r['date']==day and r['channel']==channel]
    records.sort(key=lambda r:(r['side'],r['id']))
    rules=[{'id':p.pk,'revision':p.revision,'mode':p.deposit_mode,'percentage':str(p.percentage)} for p in policies
        if p.channel==channel and (not p.valid_from or p.valid_from.isoformat()<=day) and (not p.valid_until or day<=p.valid_until.isoformat())]
    return {'company':summary['company'],'channel':channel,'day':day,'totals':values,'records':records,'policies':rules}


def attach_checks(company,summary,rows,studio=None):
    if not summary.get('supported'):return
    checks={(c.channel,c.day.isoformat()):c for c in ClosureCheck.objects.filter(company=company,day__startswith=summary['month'])}
    policies=list(FeePolicy.objects.filter(company=company,active=True))
    for method in summary['methods']:
        method['checked_days']=0;method['recheck_days']=0
        for day in method['days']:
            if studio:
                day['check']={'status':'company_scope','revision':0};continue
            evidence=snapshot(summary,rows,method['channel'],day['date'],policies);token=fingerprint(evidence)
            check=checks.get((method['channel'],day['date']))
            status='open' if not check or check.state=='open' else 'checked' if check.evidence_token==token else 'needs_recheck'
            day['check_token']=token
            day['check']={'status':status,'revision':check.revision if check else 0,'id':check.pk if check else None,
                'note':check.note if check else '', 'checked_at':check.checked_at if check else None}
            method['checked_days']+=status=='checked';method['recheck_days']+=status=='needs_recheck'


def check_state(check):
    return {'state':check.state,'revision':check.revision,'evidence_token':check.evidence_token,
        'snapshot':check.snapshot,'actor':check.actor_id,'checked_at':check.checked_at.isoformat() if check.checked_at else None,'note':check.note}


def save_check(company,actor,summary,rows,values):
    channel=values['channel'];day=values['day'].isoformat()
    current=snapshot(summary,rows,channel,day,list(FeePolicy.objects.filter(company=company,active=True)))
    token=fingerprint(current)
    if token!=values['expected_token']:raise ConfigurationConflict('Supporting records changed. Refresh the day before checking.')
    totals=current['totals']
    if totals['expected'] is None:raise ValidationError('Resolve the missing fee estimate before checking this day.')
    note=values.get('note','').strip()
    if Decimal(totals['difference'])!=0 and not note:raise ValidationError({'note':'Explain the difference before marking this day checked.'})
    check=ClosureCheck.objects.select_for_update().filter(company=company,channel=channel,day=values['day']).first()
    if check and check.state=='checked' and check.evidence_token==token:return check
    if check and check.state=='checked':raise ValidationError('An authorized user must reopen this day before checking it again.')
    if (check.revision if check else 0)!=values['expected_revision']:raise ConfigurationConflict('This check changed. Refresh before saving.')
    before=check_state(check) if check else {}
    if not check:check=ClosureCheck(company=company,channel=channel,day=values['day'])
    else:check.revision+=1
    check.state='checked';check.evidence_token=token;check.snapshot=current;check.note=note;check.actor=actor;check.checked_at=timezone.now();check.save()
    ClosureCheckEvent.objects.create(closure=check,actor=actor,action='check',before=before,after=check_state(check),note=note)
    return check


def reopen(company,actor,values):
    check=ClosureCheck.objects.select_for_update().filter(company=company,channel=values['channel'],day=values['day']).first()
    if not check or check.revision!=values['expected_revision'] or check.state!='checked':raise ConfigurationConflict('This check changed. Refresh before reopening.')
    before=check_state(check);check.state='open';check.revision+=1;check.save(update_fields=['state','revision'])
    ClosureCheckEvent.objects.create(closure=check,actor=actor,action='reopen',before=before,after=check_state(check),note=values.get('note',''))
    return check
