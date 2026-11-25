"""Saved planning drafts, signed previews and explicit atomic shift publication."""
from collections import Counter
from datetime import datetime, time, timedelta
from hashlib import sha256
import json
import logging
from zoneinfo import ZoneInfo
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .access import ManagerWrite, manager, org, audit
from .models import DutyRoster, DutyShift, Organization, Membership
from .roster import date_value, days_between, active_mechanics, get_config, with_leave, on_leave

log=logging.getLogger(__name__)
SALT='core.duty.planner.v1'
def require(request):
    if not manager(request.user): raise PermissionDenied()
    if request.method!='GET' and not isinstance(request.data,dict): raise ValidationError('Укажите настройки.')
    return org(request.user)
def normalize(raw,company):
    if not isinstance(raw,dict): raise ValidationError('Укажите настройки смен.')
    first,last=date_value(raw.get('from')),date_value(raw.get('to'));days_between(first,last)
    clock=raw.get('start_time',company.duty_start.strftime('%H:%M'))
    try:
        if not isinstance(clock,str) or len(clock)!=5: raise ValueError()
        start_time=time.fromisoformat(clock)
    except ValueError: raise ValidationError('Укажите время начала смены ЧЧ:ММ.')
    if raw.get('mode','daily') not in ('daily','split'): raise ValidationError('Выберите суточные смены или день / ночь.')
    mechanics=active_mechanics(company);ids=raw.get('people')
    if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(type(x)is not int or x not in mechanics for x in ids) or len(set(ids))!=len(ids): raise ValidationError('Выберите до 100 действующих механиков без повторов.')
    overrides=raw.get('overrides',{})
    if not isinstance(overrides,dict) or len(overrides)>732 or any(not isinstance(k,str) or len(k)>20 or type(v)is not int or v not in mechanics for k,v in overrides.items()): raise ValidationError('Проверьте подмены по датам.')
    if type(raw.get('replace_existing',False))is not bool: raise ValidationError('Проверьте настройку пересчёта назначений.')
    return {'from':first.isoformat(),'to':last.isoformat(),'start_time':start_time.strftime('%H:%M'),'mode':raw.get('mode','daily'),'people':ids,'overrides':overrides,'replace_existing':raw.get('replace_existing',False)}

def state(company):
    row,_=DutyRoster.objects.get_or_create(organization=company,defaults={'config':{'cycles':[],'periods':[]}})
    return row

@api_view(['GET','PUT'])
@permission_classes([ManagerWrite])
def draft(request):
    company=require(request)
    with transaction.atomic():
        company=Organization.objects.select_for_update().get(pk=company.pk);row=state(company)
        if request.method=='PUT':
            if type(request.data.get('revision'))is not int or request.data['revision']!=row.planning_revision: raise ValidationError('Черновик изменился. Загрузите актуальные настройки.')
            row.draft=normalize(request.data.get('draft'),company);row.planning_revision+=1;row.save(update_fields=['draft','planning_revision'])
            audit(request.user,'duty.planner.draft',company.pk,{'revision':row.planning_revision})
        config=get_config(company);cycle=next(iter(reversed(config.get('cycles',[]))),None)
        return Response({'draft':row.draft,'revision':row.planning_revision,'queue':cycle.get('people',[]) if cycle else [],'duty_start':company.duty_start.strftime('%H:%M'),'legacy_periods':len(config.get('periods',[]))},headers={'Cache-Control':'private, no-store'})

def compute(company,plan):
    zone=ZoneInfo(company.timezone);clock=time.fromisoformat(plan['start_time']);days=days_between(date_value(plan['from']),date_value(plan['to']))
    start=datetime.combine(days[0],clock,zone);end=datetime.combine(days[-1]+timedelta(days=1),clock,zone)
    existing=list(DutyShift.objects.filter(organization=company,start__lt=end,end__gt=start).select_related('technician').prefetch_related('swaps').order_by('start','id'))
    config=with_leave(get_config(company),company);mechanics=active_mechanics(company);now=timezone.now();rows=[];counts=Counter();index=0
    for day in days:
        for part in range(2 if plan['mode']=='split' else 1):
            begin=datetime.combine(day,clock,zone)+timedelta(hours=12*part);finish=begin+timedelta(hours=12 if plan['mode']=='split' else 24)
            kind=('day' if part==0 else 'night') if plan['mode']=='split' else 'daily';key=day.isoformat()+'/'+kind
            expected=plan['people'][index%len(plan['people'])];index+=1
            unavailable=[pk for pk in mechanics if on_leave(config,pk,begin,finish,company)]
            conflicts=[s for s in existing if s.start<finish and s.end>begin]
            shift=conflicts[0] if len(conflicts)==1 and conflicts[0].start==begin and conflicts[0].end==finish else None
            past=begin<=now
            protected=bool(shift and (past or shift.acknowledged_at or list(shift.swaps.all())))
            error='';note='';chosen=None;replacement=False
            if past:
                chosen=shift.technician_id if shift else None;note='Смена началась — сохранена'
            elif conflicts and not shift:
                error='Пересечение со сменой другого формата. Выберите другой период.'
            elif shift and (protected or not plan['replace_existing']):
                chosen=shift.technician_id;note='Смена с историей — сохранена' if protected else 'Опубликованное назначение сохранено'
                if chosen in unavailable: error='Назначенный механик в отпуске. Разрешите пересчёт или измените подмену.'
            else:
                chosen=plan['overrides'].get(key)
                if chosen is not None and chosen in unavailable: error='Выбранный механик в отпуске.'
                if chosen is None:
                    chosen=expected if expected not in unavailable else None
                    if chosen is None:
                        available=[pk for pk in plan['people'] if pk not in unavailable]
                        if available: chosen=min(available,key=lambda pk:(counts[pk],pk==rows[-1]['technician'] if rows else False,plan['people'].index(pk)))
                        replacement=True;note=mechanics.get(expected,'Механик')+' — отпуск'
                if chosen is None: error='Нет доступного механика. Выберите подмену или добавьте сотрудника.'
                if key in plan['overrides']: note='Ручное назначение';replacement=chosen!=expected
            if chosen: counts[chosen]+=1
            changed=not past and not error and chosen is not None and (not shift or shift.technician_id!=chosen)
            rows.append({'key':key,'date':day.isoformat(),'kind':kind,'start':begin.isoformat(),'end':finish.isoformat(),'technician':chosen,'name':mechanics.get(chosen,shift.technician.full_name if shift else ''),'expected_name':mechanics.get(expected,''),'old_name':shift.technician.full_name if shift else '', 'shift':shift.pk if shift else None,'unavailable':unavailable,'replacement':replacement,'note':note,'error':error,'protected':protected or past,'changed':changed})
    unknown=set(plan['overrides'])-{r['key'] for r in rows}
    if unknown: raise ValidationError('Подмена относится к другому периоду. Очистите назначения и проверьте даты.')
    fingerprint=sha256(json.dumps([plan,rows,[(s.pk,str(s.updated_at),str(s.acknowledged_at),[(w.pk,w.status) for w in s.swaps.all()]) for s in existing]],sort_keys=True).encode()).hexdigest()
    return rows,[{'id':pk,'name':mechanics[pk],'count':counts[pk]} for pk in dict.fromkeys([*plan['people'],*counts])],fingerprint

@api_view(['POST'])
@permission_classes([ManagerWrite])
def preview(request):
    company=require(request);plan=normalize(request.data.get('draft'),company)
    with transaction.atomic():
        company=Organization.objects.select_for_update().get(pk=company.pk);stored=state(company)
        rows,summary,fingerprint=compute(company,plan)
        token=signing.dumps([company.pk,request.user.pk,stored.planning_revision,fingerprint],salt=SALT)
        return Response({'rows':rows,'summary':summary,'token':token,'revision':stored.planning_revision,'added':sum(r['changed'] and not r['shift'] for r in rows),'updated':sum(r['changed'] and bool(r['shift']) for r in rows),'missing':sum(bool(r['error']) for r in rows)},headers={'Cache-Control':'private, no-store'})

@api_view(['POST'])
@permission_classes([ManagerWrite])
def publish(request):
    company=require(request);plan=normalize(request.data.get('draft'),company)
    with transaction.atomic():
        company=Organization.objects.select_for_update().get(pk=company.pk);stored=state(company)
        rows,summary,fingerprint=compute(company,plan)
        try: valid=signing.loads(request.data.get('token',''),salt=SALT,max_age=1800)==[company.pk,request.user.pk,stored.planning_revision,fingerprint]
        except (signing.BadSignature,TypeError): valid=False
        if not valid: raise ValidationError('План изменился или проверка устарела. Пересчитайте распределение.')
        if any(r['error'] for r in rows): raise ValidationError('Сначала устраните незаполненные смены и пересечения.')
        added=updated=0;affected=set()
        for row in rows:
            if not row['changed']: continue
            if row['shift']:
                shift=DutyShift.objects.get(organization=company,pk=row['shift']);affected.add(shift.technician_id);shift.technician_id=row['technician'];shift.save(update_fields=['technician','updated_at']);updated+=1
            else:
                DutyShift.objects.create(organization=company,technician_id=row['technician'],start=datetime.fromisoformat(row['start']),end=datetime.fromisoformat(row['end']),kind=row['kind'],roster_generated=True);added+=1
            affected.add(row['technician'])
        stored.draft={**plan,'published':True};stored.planning_revision+=1
        config=get_config(company)
        # Queue continues beyond the published range; history of earlier cycles is preserved.
        if any(r['changed'] for r in rows):
            config['cycles']=[r for r in config.get('cycles',[]) if r['from']!=plan['from']]+[{'from':plan['from'],'people':plan['people'],'mode':plan['mode'],'start_time':plan['start_time']}]
            config['cycles'].sort(key=lambda r:r['from'])
            stored.config=config
        stored.save(update_fields=['draft','planning_revision','config'])
        e=audit(request.user,'duty.planner.publish',company.pk,{'added':added,'updated':updated,'revision':stored.planning_revision})
        if added or updated:
            from .notification_inbox import _enqueue
            users=Membership.objects.filter(organization=company,active=True,user__is_active=True,technician_id__in=affected).exclude(user=request.user).values_list('user_id',flat=True)
            _enqueue(company,users,'duty_plan',e.pk,'published','Обновлён график дежурств','duty',0,push=True,body=plan['from']+' — '+plan['to']+'. Откройте график, чтобы проверить свои смены.')
        log.info('duty_plan_published organization=%s added=%s updated=%s',company.pk,added,updated)
        return Response({'added':added,'updated':updated,'revision':stored.planning_revision})
