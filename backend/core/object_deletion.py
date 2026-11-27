"""Remove objects from selection while keeping protected work and file history."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied,ValidationError
from .access import role,org,audit
from .models import Building,Elevator


def authorize(user,data,required=False):
    if role(user) not in ('ADMIN','DIRECTOR'):
        raise PermissionDenied('Удаление объектов доступно администратору и директору.')
    text=data.get('reason','')
    text=text.strip() if isinstance(text,str) else ''
    if required and (data.get('confirm') is not True or not 5<=len(text)<=1000):
        raise ValidationError('Подтвердите удаление и укажите причину (5–1000 символов).')
    return text


@transaction.atomic
def delete_building(user,pk,data):
    authorize(user,data)
    building=get_object_or_404(Building.objects.select_for_update(),pk=pk,organization=org(user),deleted_at__isnull=True)
    lifts=list(Elevator.objects.select_for_update().filter(building=building,deleted_at__isnull=True))
    text=authorize(user,data,required=bool(lifts))
    now=timezone.now()
    Elevator.objects.filter(pk__in=[l.pk for l in lifts]).update(deleted_at=now,active=False)
    building.deleted_at=now;building.save(update_fields=['deleted_at'])
    audit(user,'building.deleted',building.pk,{'reason':text,'address':building.address,'lifts':[l.pk for l in lifts]})


@transaction.atomic
def delete_elevator(user,pk,data):
    text=authorize(user,data,required=True)
    lift=get_object_or_404(Elevator.objects.select_for_update(),pk=pk,organization=org(user),deleted_at__isnull=True)
    lift.deleted_at=timezone.now();lift.active=False;lift.save(update_fields=['deleted_at','active'])
    audit(user,'elevator.deleted',lift.pk,{'reason':text,'building':lift.building_id})
