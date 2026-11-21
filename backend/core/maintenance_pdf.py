"""Landscape technical-maintenance journal for a single authorized lift."""
import io
import logging
import os
from datetime import date, datetime, time, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .access import MemberAccess, org
from .models import Elevator, Maintenance, Ticket

logger = logging.getLogger(__name__)
_FONT = 'LiftControl-DejaVu'
TITLE = ('Журнал технического обслуживания лифта, подъёмной платформы для инвалидов, '
         'пассажирского конвейера (движущейся пешеходной дорожки), эскалатора.')
HEADERS = (
    '№ п/п', 'Вид проведённой работы', 'Дата проведения работы',
    'Ф.И.О., должность лица, выполнившего работы',
    'Подпись лица, выполнившего работы',
    'Подпись лица, ответственного за организацию обслуживания и ремонт объекта',
)
MAX_ROWS = 1000
_FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def _font():
    if _FONT not in pdfmetrics.getRegisteredFontNames():
        font_path = Path(os.getenv('LIFTCONTROL_PDF_FONT', _FONT_PATH))
        if not font_path.is_file():
            raise RuntimeError('Cyrillic PDF font is not installed on the server')
        pdfmetrics.registerFont(TTFont(_FONT, str(font_path)))


def _date(value, key):
    if not value:
        return None
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({key: 'Ожидается дата ГГГГ-ММ-ДД.'})


def _paragraph(value, style):
    return Paragraph(escape(str(value or '—')).replace('\n', '<br/>'), style)


def _pdf(lift, rows, organization, start, end):
    _font()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=13*mm, bottomMargin=37*mm,
        leftMargin=12*mm, rightMargin=12*mm,
        title='Журнал технического обслуживания лифта',
        author='LiftControl',
    )
    width = doc.width - 12
    title_style = ParagraphStyle('LCTitle',fontName=_FONT,fontSize=14,leading=18,alignment=TA_CENTER,spaceAfter=9)
    normal = ParagraphStyle('LCText',fontName=_FONT,fontSize=8,leading=11,alignment=TA_LEFT,spaceAfter=3)
    head = ParagraphStyle('LCHead',parent=normal,fontSize=7.5,leading=10,alignment=TA_CENTER)
    cells = ParagraphStyle('LCCell',parent=normal,fontSize=7.5,leading=10,spaceAfter=0)
    cover_text = ParagraphStyle('LCCover', parent=normal, fontSize=11, leading=16)
    cover = Table([
        [_paragraph('Специализированная организация', cover_text),
         [_paragraph(organization.name, cover_text),
          _paragraph('(наименование и организационно-правовая форма юридического лица '
                     'или Ф.И.О. индивидуального предпринимателя)', normal)]],
        [_paragraph('Адрес объекта', cover_text), _paragraph(lift.building.address, cover_text)],
        [_paragraph('Наименование и тип объекта', cover_text),
         [_paragraph(' · '.join(filter(None, ('Лифт', lift.get_elevator_type_display(), lift.model))), cover_text),
          _paragraph('(лифт, платформа подъёмная для инвалидов, пассажирский конвейер, эскалатор)', normal)]],
        [_paragraph('Заводской номер объекта', cover_text), _paragraph(lift.factory_number, cover_text)],
    ], colWidths=[width * .36, width * .64], hAlign='CENTER')
    cover.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (1, 0), (1, -1), .5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story = [
        Spacer(1, 19*mm),
        _paragraph(TITLE, title_style),
        Spacer(1, 16*mm),
        cover,
        Spacer(1, 9*mm),
    ]
    if start or end:
        period = ' — '.join(d.strftime('%d.%m.%Y') if d else '…' for d in (start, end))
        story.append(_paragraph(f'Период: {period}', cover_text))
    story.append(PageBreak())
    data = [[_paragraph(label, head) for label in HEADERS],
            [_paragraph(i, head) for i in range(1, 7)]]
    for number, row in enumerate(rows, 1):
        work_date = date.fromisoformat(row['date']).strftime('%d.%m.%Y')
        data.append([
            _paragraph(number, cells), _paragraph(row['description'], cells),
            _paragraph(work_date, cells), _paragraph(row['performer'], cells), '', '',
        ])
    row_heights = None
    if not rows:
        data.extend([[''] * 6 for _ in range(19)])
        row_heights = [None, None] + [15] * 19
    proportions = (.041, .237, .164, .276, .141, .141)
    table = Table(
        data, colWidths=[width * part for part in proportions], rowHeights=row_heights,
        repeatRows=2, splitInRow=1, hAlign='LEFT',
    )
    table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.4,colors.black),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LEFTPADDING',(0,0),(-1,-1),5),
        ('RIGHTPADDING',(0,0),(-1,-1),5),
    ]))
    story.append(table)
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(_FONT, 7.5)
        page_width, _ = landscape(A4)
        right = page_width - 12*mm
        if document.page > 1:
            left = 12*mm + 6
            canvas.drawString(left, 29*mm, 'Для дополнительных замечаний:')
            canvas.setLineWidth(.4)
            for y in (24, 18, 12):
                canvas.line(left, y*mm, left + width, y*mm)
        canvas.drawRightString(right, 6*mm, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _journal(request, elevator_id):
    organization = org(request.user)
    lift = get_object_or_404(Elevator.objects.select_related('building'),
                             pk=elevator_id, organization=organization)
    start = _date(request.query_params.get('from'), 'from')
    end = _date(request.query_params.get('to'), 'to')
    if start and end and end < start:
        raise ValidationError({'to': 'Дата окончания раньше даты начала.'})

    local_zone = ZoneInfo(organization.timezone)
    dates = {'completed_at__isnull': False}
    if start:
        dates['completed_at__gte'] = datetime.combine(start, time.min, tzinfo=local_zone)
    if end and end < date.max:
        dates['completed_at__lt'] = datetime.combine(end + timedelta(days=1), time.min, tzinfo=local_zone)
    scope = dict(dates, organization=organization, elevator=lift)
    maintenance = Maintenance.objects.filter(**scope).select_related('technician').order_by('completed_at', 'pk')
    tickets = Ticket.objects.filter(**scope, status=Ticket.Status.DONE).select_related('assigned_to').order_by(
        'completed_at', 'pk',
    )

    work = [
        (item.completed_at, 'maintenance', item.pk,
         '\n'.join(filter(None, (item.get_kind_display(), item.notes.strip()))), item.technician)
        for item in maintenance[:MAX_ROWS + 1]
    ]
    work.extend(
        (ticket.completed_at, 'ticket', ticket.pk,
         f'Заявка №{ticket.pk}: {ticket.repair.strip() or ticket.title}', ticket.assigned_to)
        for ticket in tickets[:MAX_ROWS + 1 - len(work)]
    )
    if len(work) > MAX_ROWS:
        raise ValidationError('Слишком много записей. Выберите более короткий период.')

    rows = []
    for completed_at, source, source_id, description, technician in sorted(work, key=lambda item: item[:3]):
        performer = 'Не указан'
        if technician and technician.organization_id == organization.pk:
            performer = f'{technician.full_name} / {technician.get_role_display()}'
        rows.append({
            'date': timezone.localtime(completed_at, local_zone).date().isoformat(),
            'source': source, 'source_id': source_id,
            'description': description, 'performer': performer,
        })
    return organization, lift, rows, start, end


@api_view(['GET'])
@permission_classes([MemberAccess])
def maintenance_journal(request, elevator_id):
    _, _, rows, _, _ = _journal(request, elevator_id)
    return Response({'rows': rows}, headers={'Cache-Control': 'private, no-store'})


@api_view(['GET'])
@permission_classes([MemberAccess])
def maintenance_pdf(request, elevator_id):
    organization, lift, rows, start, end = _journal(request, elevator_id)
    content = _pdf(lift, rows, organization, start, end)
    response=HttpResponse(content,content_type='application/pdf')
    response['Cache-Control']='private, no-store'
    response['Content-Disposition']=f'attachment; filename="LiftControl-TO-{lift.pk}.pdf"'
    response['X-Content-Type-Options']='nosniff'
    logger.info('maintenance_pdf_generated organization=%s elevator=%s rows=%s',
                organization.pk,lift.pk,len(rows))
    return response
