"""Issue and redeem first-password links for newly created employee accounts."""
import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.validators import MaxLengthValidator
from django.db import transaction
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from .access import role
from .models import AuditEvent, EmployeePasswordSetup, Membership, Organization


def setup_is_pending(member):
    return not member.user.has_usable_password() and hasattr(member, 'password_setup')


def setup_access_enabled(member):
    if not member.active or not member.user.is_active:
        return False
    if member.technician_id is None:
        return member.role != Membership.Role.MECHANIC
    return member.technician.active and member.technician.organization_id == member.organization_id


@sensitive_variables()
def issue_setup_link(request, member):
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)
    setup, created = EmployeePasswordSetup.objects.update_or_create(
        membership=member,
        defaults={
            'token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'expires_at': expires_at,
            'issued_by': request.user,
        },
    )
    AuditEvent.objects.create(
        organization_id=member.organization_id,
        actor=request.user,
        action='employee.password_setup_issued' if created else 'employee.password_setup_reissued',
        object_id=str(member.pk),
    )
    # Only the browser sees the fragment. Access logs receive a fixed path.
    url = request.build_absolute_uri(reverse('employee-password-setup')) + '#' + token
    return {'setup_url': url, 'setup_expires_at': setup.expires_at}


def issuer_can_provide(setup, member):
    issuer = setup.issued_by
    if issuer is None or not issuer.is_active:
        return False
    issuer._organization_id = member.organization_id
    issuer_role = role(issuer)
    return issuer_role == 'ADMIN' or (
        issuer_role == 'DIRECTOR' and member.role != Membership.Role.ADMIN
    )


@transaction.atomic
@sensitive_variables()
def redeem_setup_link(token, data):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None, None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    organization_id = EmployeePasswordSetup.objects.filter(token_hash=token_hash).values_list(
        'membership__organization_id', flat=True,
    ).first()
    if organization_id is None:
        return None, None

    # Re-read after locking so a concurrent reissue or redemption wins exactly once.
    Organization.objects.select_for_update().get(pk=organization_id)
    setup = EmployeePasswordSetup.objects.filter(token_hash=token_hash).select_related(
        'membership__technician', 'issued_by',
    ).first()
    if setup is None or setup.expires_at <= timezone.now():
        return None, None
    member = setup.membership
    account = get_user_model().objects.select_for_update().get(pk=member.user_id)
    member.user = account
    if account.has_usable_password() or not setup_access_enabled(member) or not issuer_can_provide(setup, member):
        return None, None

    form = SetPasswordForm(account, data)
    # New passwords must be usable by the Android login, which caps input at 1024.
    form.fields['new_password1'].validators.append(MaxLengthValidator(1024))
    form.fields['new_password2'].validators.append(MaxLengthValidator(1024))
    if not form.is_valid():
        return None, form
    form.save()
    setup.delete()
    AuditEvent.objects.create(
        organization_id=organization_id, actor=account,
        action='employee.password_setup_completed', object_id=str(member.pk),
    )
    return account, None


@sensitive_post_parameters()
@sensitive_variables()
@never_cache
@require_http_methods(['GET', 'POST'])
def password_setup_page(request):
    context = {}
    status = 200
    if not (request.is_secure() or settings.DEBUG):
        context['unavailable'] = 'Откройте ссылку по HTTPS.'
        status = 403
    elif request.method == 'POST':
        token = request.POST.get('token', '')
        account, form = redeem_setup_link(token, request.POST)
        if account:
            context['username'] = account.username
        elif form:
            context.update(token=token, errors=form.errors)
            status = 400
        else:
            context['unavailable'] = 'Ссылка недействительна. Попросите администратора выпустить новую.'
            status = 400
    response = render(request, 'employee_password_setup.html', context, status=status)
    # Django's HTTPS CSRF check needs a same-origin Referer if Origin is absent.
    response['Referrer-Policy'] = 'same-origin'
    return response
