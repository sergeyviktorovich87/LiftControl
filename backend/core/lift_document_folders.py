"""Legal document folders with explicit, inherited elevator links."""
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .access import MemberAccess, org, role, audit
from .models import LiftDocumentFolder, LiftDocument, Elevator, Organization
from .document_folders import descendants
PRIVATE = {'Cache-Control': 'private, no-store'}


def catalog(company):
    rows = list(LiftDocumentFolder.objects.filter(organization=company).prefetch_related('elevators'))
    by_id = {f.pk: f for f in rows}
    invalid = descendants(rows, {f.pk for f in rows if f.deleted_at or f.parent_id and f.parent_id not in by_id})
    effective = {}
    for f in rows:
        ids, seen, parent = set(), set(), f
        while parent and f.pk not in invalid:
            if parent.pk in seen:
                ids.clear()
                invalid.add(f.pk)
                break
            seen.add(parent.pk)
            ids.update(e.pk for e in parent.elevators.all() if e.organization_id == company.pk)
            parent = by_id.get(parent.parent_id)
        effective[f.pk] = ids
    return rows, effective, set(by_id)-invalid


def folder_data(f, effective):
    return {'id': f.pk, 'name': f.name, 'parent_id': f.parent_id, 'updated_at': f.updated_at,
            'deleted_at': f.deleted_at, 'elevator_ids': [e.pk for e in f.elevators.all() if e.organization_id == f.organization_id],
            'effective_elevator_ids': sorted(effective.get(f.pk, set()))}


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
def explorer(request):
    from .lift_documents import _require_admin, _item
    company = org(request.user)
    folders = LiftDocumentFolder.objects.filter(organization=company)
    docs = LiftDocument.objects.filter(organization=company).filter(Q(elevator__isnull=True)|Q(elevator__organization=company)).select_related('elevator__building')
    if request.method == 'GET':
        trash, lid = request.query_params.get('trash') == '1', request.query_params.get('elevator')
        if lid is None:
            _require_admin(request.user)
        else:
            if trash or role(request.user) == 'ADJUSTER':
                raise PermissionDenied()
            try:
                lid = int(lid)
                if lid <= 0: raise ValueError
            except ValueError:
                raise ValidationError('Некорректный лифт.')
            get_object_or_404(Elevator, pk=lid, organization=company)
        rows, effective, active = catalog(company)
        visible = [f for f in rows if (bool(f.deleted_at) if trash else f.pk in active) and (lid is None or lid in effective[f.pk])]
        if lid is not None:
            legacy = Q(folder__isnull=True, elevator_id=lid)
            if role(request.user) != 'ADMIN': legacy &= Q(category='INSPECTION')
            docs = docs.filter(Q(folder_id__in=[f.pk for f in visible]) | legacy)
        docs = docs.filter(deleted_at__isnull=not trash)
        if not trash: docs = docs.filter(Q(folder__isnull=True) | Q(folder_id__in=active))
        return Response({'folders': [folder_data(f, effective) for f in visible], 'documents': [_item(d) for d in docs]}, headers=PRIVATE)
    _require_admin(request.user)
    data = request.data
    if not isinstance(data, dict): raise ValidationError('Ожидается объект запроса.')
    for key in ('id', 'parent_id', 'target'):
        if data.get(key) is not None and (type(data[key]) is not int or data[key] <= 0): raise ValidationError('Некорректный идентификатор.')
    for key in ('folders', 'documents', 'elevator_ids'):
        ids = data.get(key, [])
        if not isinstance(ids, list) or len(ids) > (1000 if key == 'elevator_ids' else 200) or any(type(i) is not int or i <= 0 for i in ids):
            raise ValidationError('Некорректный список элементов.')
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=company.pk)
        action = data.get('action')
        rows, effective, active = catalog(company)
        if action in ('create', 'edit'):
            current = get_object_or_404(folders, pk=data.get('id'), pk__in=active) if action == 'edit' else None
            name = data.get('name', current.name if current else '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200 or any(c in name for c in '/\\\x00'): raise ValidationError('Название папки: 1–200 символов, без слешей.')
            pid = data.get('parent_id', current.parent_id if current else None)
            parent = get_object_or_404(folders, pk=pid, pk__in=active) if pid else None
            if current and parent and parent.pk in descendants(rows, [current.pk]): raise ValidationError('Нельзя переместить папку в себя или её вложенную папку.')
            ids = set(data.get('elevator_ids', current.elevators.values_list('pk', flat=True) if current else []))
            elevators = list(Elevator.objects.filter(organization=company, pk__in=ids))
            if len(elevators) != len(ids): raise ValidationError('Лифт отсутствует в этой организации.')
            if current:
                current.name, current.parent, current.updated_at = name.strip(), parent, timezone.now()
                current.save()
            else: current = LiftDocumentFolder.objects.create(organization=company, name=name.strip(), parent=parent)
            current.elevators.set(elevators)
            audit(request.user, 'lift_document.folder.'+action, current.pk, {'elevators': sorted(ids)})
            _, effective, _ = catalog(company)
            return Response(folder_data(current, effective), headers=PRIVATE)
        if action not in ('move','copy','delete','restore'): raise ValidationError('Неизвестное действие.')
        fids, dids = set(data.get('folders', [])), set(data.get('documents', []))
        if not 1 <= len(fids)+len(dids) <= 200: raise ValidationError('Выберите от 1 до 200 элементов.')
        trash = action == 'restore'
        selected = list(folders.filter(pk__in=fids, deleted_at__isnull=not trash))
        selected_docs = list(docs.filter(pk__in=dids, deleted_at__isnull=not trash))
        if len(selected) != len(fids) or len(selected_docs) != len(dids): raise ValidationError('Элементы отсутствуют или уже изменены.')
        affected = descendants([f for f in rows if f.pk in active], fids)
        now = timezone.now()
        if action == 'delete':
            reason = data.get('reason', '')
            if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 1000: raise ValidationError('Укажите причину удаления (5–1000 символов).')
            folders.filter(pk__in=affected).update(deleted_at=now, updated_at=now)
            docs.filter(Q(pk__in=dids)|Q(folder_id__in=affected), deleted_at=None).update(deleted_at=now, updated_at=now)
        elif action == 'restore':
            restored = set(fids)
            for f in selected: restored |= descendants([r for r in rows if r.deleted_at == f.deleted_at], [f.pk])
            for f in selected:
                if f.parent_id and f.parent_id not in restored and folders.filter(pk=f.parent_id, deleted_at__isnull=False).exists(): raise ValidationError('Сначала восстановите родительскую папку.')
                subtree = descendants([r for r in rows if r.deleted_at == f.deleted_at], [f.pk])
                docs.filter(folder_id__in=subtree, deleted_at=f.deleted_at).update(deleted_at=None, updated_at=now)
            if any(d.folder_id and d.folder_id not in restored and folders.filter(pk=d.folder_id, deleted_at__isnull=False).exists() for d in selected_docs): raise ValidationError('Сначала восстановите папку документа.')
            folders.filter(pk__in=restored).update(deleted_at=None, updated_at=now)
            docs.filter(pk__in=dids).update(deleted_at=None, updated_at=now)
        else:
            target = get_object_or_404(folders, pk=data['target'], pk__in=active) if data.get('target') else None
            if target and target.pk in affected: raise ValidationError('Выберите папку вне выделенного дерева.')
            roots = [f for f in selected if f.parent_id not in affected]
            if action == 'move':
                for f in roots:
                    f.parent, f.updated_at = target, now
                    f.save(update_fields=['parent','updated_at'])
                docs.filter(pk__in=dids).update(folder=target, elevator=None, updated_at=now)
            else:
                mapping, pending = {}, [f for f in rows if f.pk in affected]
                while pending:
                    ready = [f for f in pending if f.parent_id not in affected or f.parent_id in mapping]
                    if not ready: raise ValidationError('Повреждена структура папок.')
                    for f in ready:
                        new = LiftDocumentFolder.objects.create(organization=company, name=f.name[:190]+' — копия' if f in roots else f.name, parent=mapping.get(f.parent_id, target))
                        new.elevators.set(f.elevators.all()); mapping[f.pk] = new; pending.remove(f)
                for d in docs.filter(Q(pk__in=dids)|Q(folder_id__in=affected), deleted_at=None).distinct():
                    LiftDocument.objects.create(organization=company, title=d.title, category=d.category, folder=mapping.get(d.folder_id, target), file=d.file.name)
        audit(request.user, 'lift_document.explorer.'+action, '', {'folders': sorted(fids), 'documents': sorted(dids)})
        return Response({'ok': True}, headers=PRIVATE)
