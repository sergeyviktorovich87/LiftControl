"""Tenant-scoped vacation requests. Approved time off never rewrites shifts."""
import csv
import io
import logging
from datetime import datetime, time, timedelta
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .access import MemberAccess, org, role, membership, audit
from .models import Membership, Organization, VacationRequest, VacationEvent, DutyShift, Technician
from .roster import date_value, days_between

log = logging.getLogger(__name__)
LABELS = {'DRAFT':'Черновик','PENDING':'На согласовании','APPROVED':'Согласован','REJECTED':'Отклонён','CHANGES':'Предложены другие даты','CANCELLED':'Отменён'}
def approver(user):
    return role(user) in ('ADMIN', 'DIRECTOR')
def people(company):
    return Membership.objects.filter(organization=company, active=True, user__is_active=True).select_related('user','technician').exclude(role='MECHANIC', technician__isnull=True).exclude(role='MECHANIC', technician__active=False).filter(Q(technician__isnull=True)|Q(technician__organization=company))
def owns(item, user):
    return item.employee_id == user.pk or (not item.employee_id and item.technician_id and getattr(membership(user),'technician_id',None)==item.technician_id)
def serialize(item, user, detail=False):
    private = approver(user) or owns(item,user)
    row = {'id':item.pk,'employee':item.employee_id,'technician':item.technician_id,'name':item.employee_name,'start':item.start,'end':item.end,'status':item.status,'revision':item.revision,'own':owns(item,user),'can_edit':private,'can_review':approver(user),'comment':item.comment if private else '', 'response':item.response if private else ''}
    if detail and private:
        row['history']=[{'id':e.pk,'action':e.action,'at':e.created_at,'actor':e.actor.get_full_name() or e.actor.username if e.actor else 'Перенос прежнего плана','details':e.details} for e in item.events.select_related('actor').order_by('-id')]
    return row

def event(item,user,action,details=None):
    e=VacationEvent.objects.create(vacation=item,actor=user,action=action,details=details or {'start':str(item.start),'end':str(item.end),'status':item.status,'response':item.response})
    audit(user,'vacation.'+action,item.pk,{'revision':item.revision})
    from .notification_inbox import _enqueue
    recipients=set(people(item.organization).filter(role__in=['ADMIN','DIRECTOR']).values_list('user_id',flat=True)) if item.status=='PENDING' or action=='cancel' else set()
    if item.employee_id: recipients.add(item.employee_id)
    recipients.discard(user.pk)
    if item.status!='DRAFT':
        _enqueue(item.organization,recipients,'vacation',e.pk,action,'Отпуск: '+item.employee_name,'vacation',item.pk,push=True,body=f'{item.start:%d.%m.%Y} — {item.end:%d.%m.%Y} · {LABELS[item.status]}')
    log.info('vacation_action organization=%s id=%s action=%s revision=%s',item.organization_id,item.pk,action,item.revision)

def values(data,company):
    first,last=date_value(data.get('start')),date_value(data.get('end'))
    days_between(first,last)
    if first < timezone.localdate(timezone=ZoneInfo(company.timezone)):
        raise ValidationError('Выберите сегодняшний день или будущую дату.')
    comment=data.get('comment','')
    if not isinstance(comment,str) or len(comment)>2000: raise ValidationError('Комментарий — до 2000 символов.')
    return first,last,comment.strip()

def check_overlaps(item):
    query=VacationRequest.objects.filter(organization=item.organization,status='APPROVED',start__lte=item.end,end__gte=item.start).exclude(pk=item.pk)
    own=Q(employee_id=item.employee_id) if item.employee_id else Q(pk__in=[])
    if item.technician_id: own|=Q(technician_id=item.technician_id)
    if query.filter(own).exists(): raise ValidationError('У сотрудника уже согласован отпуск на эти даты.')

def shifts_for(item):
    if not item.technician_id: return DutyShift.objects.none()
    zone=ZoneInfo(item.organization.timezone)
    first=datetime.combine(item.start,item.organization.duty_start,zone)
    end=datetime.combine(item.end+timedelta(days=1),item.organization.duty_start,zone)
    return DutyShift.objects.filter(organization=item.organization,technician_id=item.technician_id,start__lt=end,end__gt=first)

@api_view(['GET','POST'])
@permission_classes([MemberAccess])
def requests(request):
    company=org(request.user)
    if request.method=='GET':
        first=date_value(request.query_params.get('from'));last=date_value(request.query_params.get('to'));days_between(first,last)
        rows=VacationRequest.objects.filter(organization=company,start__lte=last,end__gte=first)
        if not approver(request.user): rows=rows.filter(Q(status='APPROVED')|Q(employee=request.user))
        return Response({'items':[serialize(r,request.user) for r in rows.order_by('start','employee_name')[:3000]],'people':[{'user':m.user_id,'technician':m.technician_id,'name':m.user.get_full_name() or m.technician.full_name if m.technician else m.user.get_full_name() or m.user.username} for m in people(company)],'can_review':approver(request.user)},headers={'Cache-Control':'private, no-store'})
    if not isinstance(request.data,dict): raise ValidationError('Укажите параметры отпуска.')
    first,last,comment=values(request.data,company)
    status=request.data.get('status','DRAFT')
    if status not in ('DRAFT','PENDING'): raise ValidationError('Сначала сохраните черновик или отправьте заявку.')
    employee=request.data.get('employee',request.user.pk)
    if type(employee) is not int or (employee!=request.user.pk and not approver(request.user)): raise PermissionDenied()
    member=get_object_or_404(people(company),user_id=employee)
    try: operation=UUID(str(request.data.get('operation_id')))
    except (ValueError,TypeError): raise ValidationError('Нужен идентификатор операции.')
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=company.pk)
        old=VacationRequest.objects.filter(organization=company,operation_id=operation).first()
        if old:
            if old.created_by_id!=request.user.pk or (old.employee_id,old.start,old.end,old.comment)!=(employee,first,last,comment): raise ValidationError('Идентификатор уже использован для другой заявки.')
            return Response(serialize(old,request.user,True))
        item=VacationRequest.objects.create(organization=company,employee_id=employee,technician_id=member.technician_id,employee_name=member.technician.full_name if member.technician else member.user.get_full_name() or member.user.username,start=first,end=last,comment=comment,status=status,operation_id=operation,created_by=request.user)
        event(item,request.user,'submit' if status=='PENDING' else 'draft')
    return Response(serialize(item,request.user,True),status=201)

@api_view(['GET','POST'])
@permission_classes([MemberAccess])
def detail(request,pk):
    company=org(request.user)
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=company.pk)
        item=get_object_or_404(VacationRequest.objects.select_related('organization'),organization=company,pk=pk)
        private=approver(request.user) or owns(item,request.user)
        if not private and item.status!='APPROVED': raise PermissionDenied()
        if request.method=='GET':
            row=serialize(item,request.user,True)
            if approver(request.user):
                row['shifts']=[{'id':s.pk,'start':s.start,'end':s.end} for s in shifts_for(item).filter(start__gt=timezone.now()).order_by('start')]
                row['overlaps']=[{'name':v.employee_name,'start':v.start,'end':v.end} for v in VacationRequest.objects.filter(organization=company,status='APPROVED',start__lte=item.end,end__gte=item.start).exclude(pk=pk)[:50]]
            return Response(row,headers={'Cache-Control':'private, no-store'})
        if not private: raise PermissionDenied()
        if not isinstance(request.data,dict): raise ValidationError('Укажите действие.')
        if type(request.data.get('revision')) is not int or request.data['revision']!=item.revision: raise ValidationError('Заявка изменилась. Откройте её заново.')
        action=request.data.get('action')
        if action in ('approve','reject','propose'):
            if not approver(request.user): raise PermissionDenied()
            if item.status!='PENDING': raise ValidationError('Решение доступно только для заявки на согласовании.')
            response=request.data.get('response','')
            if not isinstance(response,str) or len(response)>2000 or (action!='approve' and not response.strip()): raise ValidationError('Добавьте пояснение до 2000 символов.')
            item.response=response.strip()
            if action=='approve':
                if item.end<timezone.localdate(timezone=ZoneInfo(company.timezone)): raise ValidationError('Период уже закончился.')
                check_overlaps(item)
                # No duty mutations here. Review/publish handles replacements separately.
                item.status='APPROVED'
            elif action=='reject': item.status='REJECTED'
            else:
                first,last,_=values({**request.data,'comment':''},company)
                item.response=f'Предложенные даты: {first:%d.%m.%Y} — {last:%d.%m.%Y}. '+item.response
                item.status='CHANGES'
        elif action=='save' or action=='submit':
            if item.status not in ('DRAFT','CHANGES','REJECTED'): raise ValidationError('Для переноса согласованного отпуска отмените прежний и отправьте новую заявку.')
            item.start,item.end,item.comment=values(request.data,company)
            item.status='PENDING' if action=='submit' else 'DRAFT'
            item.response=''
        elif action=='cancel':
            if item.status=='APPROVED' and not approver(request.user): raise PermissionDenied('Отмену согласованного отпуска подтверждает руководитель.')
            if item.status=='CANCELLED': raise ValidationError('Отпуск уже отменён.')
            item.status='CANCELLED'
        else: raise ValidationError('Выберите действие.')
        item.revision+=1;item.save();event(item,request.user,action)
        return Response(serialize(item,request.user,True))

@api_view(['GET'])
@permission_classes([MemberAccess])
def export(request):
    company=org(request.user)
    first,last=date_value(request.query_params.get('from')),date_value(request.query_params.get('to'));days_between(first,last)
    rows=VacationRequest.objects.filter(organization=company,status='APPROVED',start__lte=last,end__gte=first).order_by('employee_name','start')[:3000]
    table=[['Сотрудник','Начало','Окончание','Статус']]+[[r.employee_name,r.start.strftime('%d.%m.%Y'),r.end.strftime('%d.%m.%Y'),'Согласован'] for r in rows]
    if request.query_params.get('file')=='pdf':
        from .maintenance_pdf import _font,_FONT
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer
        from reportlab.lib.styles import ParagraphStyle
        _font();output=io.BytesIO();style=ParagraphStyle('body',fontName=_FONT,fontSize=9,leading=13)
        content=[Paragraph('План отпусков · '+escape(company.name),style),Paragraph(f'{first:%d.%m.%Y} — {last:%d.%m.%Y}',style),Spacer(1,16)]
        t=Table([[Paragraph(escape(str(cell)),style) for cell in row] for row in table],colWidths=[240,85,85,85],repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),'#e6eee8'),('GRID',(0,0),(-1,-1),.3,'#d3ddd5'),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),9)]));content.append(t)
        SimpleDocTemplate(output,pagesize=A4,rightMargin=40,leftMargin=40).build(content)
        response=HttpResponse(output.getvalue(),content_type='application/pdf');suffix='pdf'
    else:
        output=io.StringIO();writer=csv.writer(output,delimiter=';')
        writer.writerows([["'"+v if isinstance(v,str) and (v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n'))) else v for v in row] for row in table])
        response=HttpResponse('\ufeff'+output.getvalue(),content_type='text/csv; charset=utf-8');suffix='csv'
    response['Content-Disposition']=f'attachment; filename="LiftControl-vacations.{suffix}"';response['Cache-Control']='private, no-store'
    return response
