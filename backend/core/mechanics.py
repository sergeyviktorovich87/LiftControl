"""Tenant-scoped mechanic directory and reviewed lift assignments."""
import io
import logging
import re
from html import escape
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .access import MemberAccess, OwnerWrite, org, audit
from .models import Organization, Technician, Elevator, Ticket, DutyShift, VacationRequest
from .serializers import ElevatorSerializer

log = logging.getLogger(__name__)
IN_WORK = ('IN_PROGRESS', 'STOPPED', 'LONG_REPAIR')
OPEN = ('NEW', 'ASSIGNED', *IN_WORK)

def archived(request):
    value = request.query_params.get('include_archived', '0')
    if value not in ('0', '1'):
        raise ValidationError('Проверьте настройку архива.')
    return value == '1'

def mechanic(company, pk):
    return get_object_or_404(Technician, organization=company, pk=pk, role='MECHANIC')

def lift_label(item):
    value = item.entrance.strip()
    if item.entrance_kind == 'LIFT':
        return value if value.lower().startswith('лифт') else 'Лифт №'+value if value else 'Номер лифта не указан'
    return value if value.lower().startswith('подъезд') else 'Подъезд '+value if value else 'Подъезд не указан'

def natural(value):
    return [(1,int(p)) if p.isdigit() else (0,p.casefold()) for p in re.split(r'(\d+)',value or '')]

@api_view(['GET'])
@permission_classes([MemberAccess])
def overview(request):
    company = org(request.user)
    workers = Technician.objects.filter(organization=company,role='MECHANIC')
    if not archived(request):
        workers = workers.filter(active=True)
    lift_counts, addresses = {}, {}
    for lift in Elevator.objects.filter(organization=company,building__organization=company,active=True).select_related('building'):
        pk = lift.assigned_technician_id
        if pk:
            lift_counts[pk] = lift_counts.get(pk,0)+1
            addresses.setdefault(pk,set()).add(lift.building.address)
    tickets = dict(Ticket.objects.filter(organization=company,elevator__organization=company,
        elevator__building__organization=company,assigned_to__organization=company,status__in=IN_WORK
    ).values('assigned_to_id').annotate(count=Count('pk')).values_list('assigned_to_id','count'))
    now = timezone.now()
    duty = set(DutyShift.objects.filter(organization=company,start__lte=now,end__gt=now).values_list('technician_id',flat=True))
    today = timezone.localdate(timezone=ZoneInfo(company.timezone))
    leave = {}
    for item in VacationRequest.objects.filter(organization=company,status='APPROVED',start__lte=today,end__gte=today,technician__organization=company):
        leave[item.technician_id] = max(item.end,leave.get(item.technician_id,item.end))
    rows = []
    for worker in workers.order_by('full_name','id'):
        status = 'ARCHIVED' if not worker.active else 'VACATION' if worker.pk in leave else 'DUTY' if worker.pk in duty else 'ACTIVE'
        rows.append({'id':worker.pk,'full_name':worker.full_name,'active':worker.active,'role':worker.role,
            'status':status,'on_duty':worker.pk in duty,'leave_until':leave.get(worker.pk),
            'in_work':tickets.get(worker.pk,0),'lift_count':lift_counts.get(worker.pk,0),
            'addresses':sorted(addresses.get(worker.pk,set()))})
    return Response(rows,headers={'Cache-Control':'private, no-store'})

def assigned(request,company,worker):
    query = request.query_params.get('q','').strip()
    status = request.query_params.get('status','all')
    if len(query)>200 or status not in ('all','working','stopped'):
        raise ValidationError('Проверьте поиск и фильтр состояния.')
    lifts = Elevator.objects.filter(organization=company,building__organization=company,assigned_technician=worker).select_related('building','assigned_technician')
    if not archived(request):
        lifts = lifts.filter(active=True)
    rows = list(lifts)
    total, buildings = len(rows),len({row.building_id for row in rows})
    needle = query.casefold()
    rows = [row for row in rows if (not needle or needle in ' '.join(filter(None,[row.building.address,row.building.name,row.entrance,row.inventory_number,row.factory_number])).casefold()) and
        (status=='all' or status=='working' and row.active and not row.stopped_at or status=='stopped' and row.active and row.stopped_at)]
    rows.sort(key=lambda row:(natural(row.building.address),row.building_id,natural(row.entrance),natural(row.inventory_number),row.pk))
    return rows,total,buildings

@api_view(['GET'])
@permission_classes([MemberAccess])
def lifts(request,pk):
    company = org(request.user)
    worker = mechanic(company,pk)
    rows,total,buildings = assigned(request,company,worker)
    try:
        page = int(request.query_params.get('page','1'))
        if not 1<=page<=100000:
            raise ValueError()
    except ValueError:
        raise ValidationError('Некорректная страница.')
    count = len(rows)
    pages = max(1,(count+24)//25)
    page = min(page,pages)
    selected = rows[(page-1)*25:page*25]
    counts = dict(Ticket.objects.filter(organization=company,elevator__in=selected,status__in=OPEN).values('elevator_id').annotate(count=Count('pk')).values_list('elevator_id','count'))
    building_counts = {}
    for row in rows:
        building_counts[row.building_id] = building_counts.get(row.building_id,0)+1
    items = ElevatorSerializer(selected,many=True,context={'request':request}).data
    for item in items:
        item['open_tickets'] = counts.get(item['id'],0)
        item['building_lift_count'] = building_counts[item['building']]
    return Response({'employee':{'id':worker.pk,'full_name':worker.full_name,'active':worker.active},'total':total,
        'buildings':buildings,'matched':count,'page':page,'pages':pages,'items':items},headers={'Cache-Control':'private, no-store'})

@api_view(['GET'])
@permission_classes([MemberAccess])
def export(request,pk):
    company = org(request.user)
    worker = mechanic(company,pk)
    rows,_,_ = assigned(request,company,worker)
    if len(rows)>5000:
        raise ValidationError('Уточните поиск: не более 5000 лифтов в одном PDF.')
    from .maintenance_pdf import _font,_FONT
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    _font()
    style = ParagraphStyle('mechanic-list',fontName=_FONT,fontSize=9,leading=13)
    title = ParagraphStyle('mechanic-title',parent=style,fontSize=15,leading=21,spaceAfter=12)
    data = [['Адрес','Подъезд / лифт','Учётный номер','Заводской номер','Состояние']]+[
        [row.building.address,lift_label(row),'Нет' if row.inventory_number_missing else row.inventory_number or '—',row.factory_number or '—','Архив' if not row.active else 'Остановлен' if row.stopped_at else 'Работает'] for row in rows]
    table = Table([[Paragraph(escape(str(cell)),style) for cell in line] for line in data],colWidths=[220,120,115,120,105],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),'#e4eee6'),('GRID',(0,0),(-1,-1),.3,'#d4ded6'),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8)]))
    output = io.BytesIO()
    content = [Paragraph('Закреплённые лифты · '+escape(worker.full_name),title),Paragraph(escape(company.name)+' · Лифтов в списке: '+str(len(rows)),style),Spacer(1,15),table]
    def footer(canvas,doc):
        canvas.setFont(_FONT,8)
        canvas.drawRightString(800,20,'Страница '+str(doc.page))
    SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=30,rightMargin=30,topMargin=30,bottomMargin=35).build(content,onFirstPage=footer,onLaterPages=footer)
    result = HttpResponse(output.getvalue(),content_type='application/pdf')
    result['Content-Disposition']=f'attachment; filename="LiftControl-mechanic-{worker.pk}-lifts.pdf"'
    result['Cache-Control']='private, no-store'
    return result

@api_view(['POST'])
@permission_classes([OwnerWrite])
def assign(request,pk):
    company = org(request.user)
    source = mechanic(company,pk)
    changes = request.data.get('changes') if isinstance(request.data,dict) else None
    if not isinstance(changes,list) or not 1<=len(changes)<=200:
        raise ValidationError('Выберите от 1 до 200 лифтов за один раз.')
    ids = []
    for item in changes:
        if (not isinstance(item,dict) or type(item.get('elevator')) is not int or 'previous' not in item or 'technician' not in item or
            item['previous'] is not None and type(item['previous']) is not int or item['technician'] is not None and type(item['technician']) is not int):
            raise ValidationError('Укажите лифт, прежнего и нового механика.')
        if item['previous']!=source.pk and item['technician']!=source.pk:
            raise ValidationError('Изменение должно относиться к выбранному сотруднику.')
        ids.append(item['elevator'])
    if len(ids)!=len(set(ids)):
        raise ValidationError('Лифты не должны повторяться.')
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=company.pk)
        locked = {row.pk:row for row in Elevator.objects.select_for_update(of=('self',)).filter(organization=company,building__organization=company,pk__in=ids)}
        if len(locked)!=len(ids):
            raise ValidationError('Один из лифтов недоступен в этой организации.')
        targets = {item['technician'] for item in changes if item['technician'] is not None}
        valid = set(Technician.objects.filter(organization=company,role='MECHANIC',active=True,pk__in=targets).values_list('pk',flat=True))
        if valid!=targets:
            raise ValidationError('Назначать лифты можно только действующим механикам этой организации.')
        changed = []
        for item in changes:
            row = locked[item['elevator']]
            if not row.active:
                raise ValidationError('Для архивного лифта сначала восстановите обслуживание.')
            if row.assigned_technician_id!=item['previous']:
                raise ValidationError('Закрепление изменилось. Загрузите актуальные данные и проверьте список заново.')
            if item['previous']!=item['technician']:
                row.assigned_technician_id=item['technician']
                changed.append(row)
        Elevator.objects.bulk_update(changed,['assigned_technician'])
        audit(request.user,'mechanic.assignments',source.pk,{'changes':changes})
    log.info('mechanic_assignments organization=%s technician=%s count=%s',company.pk,source.pk,len(changed))
    return Response({'updated':len(changed)})
