from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied
from .models import Organization, Membership, AuditEvent


def membership(user):
    try:
        m = user.membership
        if m.active and (m.role != 'MECHANIC' or (m.technician and m.technician.active and m.technician.organization_id == m.organization_id)):
            return m
    except Membership.DoesNotExist:
        pass
    return None


def org(user):
    m = membership(user)
    if m:
        return m.organization
    if user.is_superuser:
        return Organization.objects.get(pk=1)
    raise PermissionDenied('Нет действующего доступа к организации.')


def role(user):
    if user.is_superuser:
        return 'ADMIN'
    m = membership(user)
    return m.role if m else ''


def manager(user):
    return role(user) in ('ADMIN', 'DIRECTOR', 'DISPATCHER')


def admin_user(user):
    return role(user) == 'ADMIN'


def technician_id(user):
    m = membership(user)
    return m.technician_id if m else None


class MemberAccess(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and (request.user.is_superuser or membership(request.user)))


class ManagerWrite(MemberAccess):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (request.method in SAFE_METHODS or manager(request.user))


def audit(user, action, obj_id=''):
    AuditEvent.objects.create(organization=org(user), actor=user, action=action, object_id=str(obj_id))
