"""Organization-scoped document explorer. Files are never removed by trash operations."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .access import MemberAccess, org, manager, role, audit
from .documentation import normalize_tags
from .models import DocumentFolder, Document, Elevator, Organization
from .serializers import DocumentSerializer


def folder_data(folder):
    return {key: getattr(folder, key) for key in
            ('id', 'name', 'parent_id', 'elevator_id', 'documentation_tags', 'updated_at', 'deleted_at')}


def descendants(rows, roots):
    result = set(roots)
    while True:
        extra = {f.pk for f in rows if f.parent_id in result} - result
        if not extra:
            return result
        result |= extra


def folder_values(data, organization, folders, current=None):
    name = str(data.get('name', current.name if current else '')).strip()
    if not name or len(name) > 200 or any(c in name for c in '/\\\x00'):
        raise ValidationError('Название папки: 1–200 символов, без слешей.')
    parent_id = data.get('parent_id', current.parent_id if current else None)
    parent = get_object_or_404(folders, pk=parent_id, deleted_at=None) if parent_id else None
    elevator_id = data.get('elevator_id', current.elevator_id if current else None)
    elevator = get_object_or_404(Elevator, pk=elevator_id, organization=organization) if elevator_id else None
    if current and parent and parent.pk in descendants(list(folders), [current.pk]):
        raise ValidationError('Нельзя переместить папку в себя или в её вложенную папку.')
    return dict(name=name, parent=parent, elevator=elevator,
                documentation_tags=normalize_tags(str(data.get('documentation_tags', current.documentation_tags if current else ''))))


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
def explorer(request):
    organization = org(request.user)
    folders = DocumentFolder.objects.filter(organization=organization)
    documents = Document.objects.filter(organization=organization)
    if request.method == 'GET':
        trash = request.query_params.get('trash') == '1'
        if trash and role(request.user) not in ('ADMIN', 'DIRECTOR'):
            raise PermissionDenied()
        return Response({'folders': [folder_data(f) for f in folders.filter(deleted_at__isnull=not trash)],
                         'documents': DocumentSerializer(documents.filter(deleted_at__isnull=not trash), many=True).data})
    if not manager(request.user):
        raise PermissionDenied('Изменять документацию может диспетчер, администратор или руководитель.')
    data = request.data
    if not isinstance(data, dict):
        raise ValidationError('Ожидается объект запроса.')
    for field in ('id', 'parent_id', 'elevator_id', 'target'):
        if data.get(field) is not None and (type(data[field]) is not int or data[field] <= 0):
            raise ValidationError('Некорректный идентификатор.')
    for field in ('folders', 'documents'):
        values = data.get(field, [])
        if not isinstance(values, list) or len(values) > 200 or any(type(v) is not int or v <= 0 for v in values):
            raise ValidationError('Выберите до 200 элементов с корректными идентификаторами.')
    action = data.get('action')
    with transaction.atomic():
        # Serialize tree mutations in an organization, including competing moves.
        Organization.objects.select_for_update().get(pk=organization.pk)
        if action in ('create', 'edit'):
            current = get_object_or_404(folders, pk=data.get('id'), deleted_at=None) if action == 'edit' else None
            values = folder_values(data, organization, folders, current)
            if current:
                for key, value in values.items():
                    setattr(current, key, value)
                current.updated_at = timezone.now()
                current.save()
            else:
                current = DocumentFolder.objects.create(organization=organization, **values)
            audit(request.user, 'document.folder.' + action, current.pk)
            return Response(folder_data(current))
        if action not in ('move', 'copy', 'delete', 'restore'):
            raise ValidationError('Неизвестное действие.')
        if action in ('delete', 'restore') and role(request.user) not in ('ADMIN', 'DIRECTOR'):
            raise PermissionDenied('Удаление и восстановление доступны администратору и руководителю.')
        try:
            folder_ids = {int(v) for v in data.get('folders', [])}
            document_ids = {int(v) for v in data.get('documents', [])}
        except (TypeError, ValueError):
            raise ValidationError('Некорректный список элементов.')
        if not 1 <= len(folder_ids) + len(document_ids) <= 200:
            raise ValidationError('Выберите от 1 до 200 элементов.')
        trash = action == 'restore'
        selected = list(folders.filter(pk__in=folder_ids, deleted_at__isnull=not trash))
        selected_docs = list(documents.filter(pk__in=document_ids, deleted_at__isnull=not trash))
        if len(selected) != len(folder_ids) or len(selected_docs) != len(document_ids):
            raise ValidationError('Некоторые элементы недоступны. Обновите список.')
        all_folders = list(folders)
        affected = descendants([f for f in all_folders if not f.deleted_at], folder_ids)
        now = timezone.now()
        if action == 'restore':
            # Restore only the same deletion batch, preserving older trash inside a folder.
            restored = set(folder_ids)
            for f in selected:
                restored |= descendants([x for x in all_folders if x.deleted_at == f.deleted_at], [f.pk])
            if any(f.parent_id and f.parent_id not in restored and folders.filter(pk=f.parent_id, deleted_at__isnull=False).exists() for f in selected):
                raise ValidationError('Сначала восстановите родительскую папку.')
            for f in selected:
                subtree = descendants([x for x in all_folders if x.deleted_at == f.deleted_at], [f.pk])
                documents.filter(folder_id__in=subtree, deleted_at=f.deleted_at).update(deleted_at=None, deleted_by=None, deletion_reason='')
            if any(d.folder_id and d.folder_id not in restored and folders.filter(pk=d.folder_id, deleted_at__isnull=False).exists() for d in selected_docs):
                raise ValidationError('Сначала восстановите папку документа.')
            folders.filter(pk__in=restored).update(deleted_at=None, updated_at=now)
            documents.filter(pk__in=document_ids).update(deleted_at=None, deleted_by=None, deletion_reason='', updated_at=now)
        elif action == 'delete':
            reason = str(data.get('reason', '')).strip()
            if not 5 <= len(reason) <= 1000:
                raise ValidationError('Укажите причину удаления (5–1000 символов).')
            folders.filter(pk__in=affected).update(deleted_at=now, updated_at=now)
            from django.db.models import Q
            documents.filter(Q(pk__in=document_ids) | Q(folder_id__in=affected), deleted_at=None).update(
                deleted_at=now, deleted_by=request.user, deletion_reason=reason, updated_at=now)
        else:
            target_id = data.get('target')
            target = get_object_or_404(folders, pk=target_id, deleted_at=None) if target_id else None
            elevator_id = data.get('elevator_id')
            elevator = get_object_or_404(Elevator, pk=elevator_id, organization=organization) if elevator_id else None
            if target and target.pk in affected:
                raise ValidationError('Выберите папку вне выделенного дерева.')
            roots = [f for f in selected if f.parent_id not in affected]
            if action == 'move':
                for f in roots:
                    f.parent, f.elevator, f.updated_at = target, elevator, now
                    f.save()
                documents.filter(pk__in=document_ids).update(folder=target, updated_at=now)
                if elevator and not target and document_ids:
                    raise ValidationError('Для файлов сначала создайте папку внутри лифта.')
            else:
                mapping = {}
                pending = [f for f in all_folders if f.pk in affected]
                while pending:
                    ready = [f for f in pending if f.parent_id not in affected or f.parent_id in mapping]
                    if not ready:
                        raise ValidationError('Повреждена структура папок.')
                    for f in ready:
                        parent = mapping.get(f.parent_id, target)
                        mapping[f.pk] = DocumentFolder.objects.create(organization=organization,
                            parent=parent, elevator=f.elevator if f.parent_id in affected else elevator,
                            name=f.name + ' — копия' if len(f.name) < 190 else f.name,
                            documentation_tags=f.documentation_tags)
                        pending.remove(f)
                from django.db.models import Q
                for d in documents.filter(Q(pk__in=document_ids) | Q(folder_id__in=affected), deleted_at=None):
                    Document.objects.create(organization=organization, title=d.title, manufacturer=d.manufacturer,
                        model=d.model, documentation_tags=d.documentation_tags, file=d.file.name,
                        folder=mapping.get(d.folder_id, target))
                if elevator and not target and document_ids:
                    raise ValidationError('Для файлов сначала создайте папку внутри лифта.')
        audit(request.user, 'document.explorer.' + action, '', {'folders': sorted(folder_ids), 'documents': sorted(document_ids)})
        return Response({'ok': True})
