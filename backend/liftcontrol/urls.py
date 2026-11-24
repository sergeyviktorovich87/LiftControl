from django.http import FileResponse
from django.views.decorators.http import require_safe
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView
from django.urls import include, path
from core.employee_password import password_setup_page

# Administrative configuration is reserved to superusers. Operational roles use the app.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
def service_worker(request):
    """Root-scoped worker, same origin, no external scripts."""
    response = FileResponse(
        (settings.BASE_DIR / 'static' / 'web' / 'service-worker.js').open('rb'),
        content_type='application/javascript',
    )
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


@require_safe
def pwa_asset(request, filename, content_type):
    # Fixed URL mappings only; never accepts user-supplied filesystem paths.
    response = FileResponse(
        (settings.BASE_DIR / 'static' / 'web' / filename).open('rb'),
        content_type=content_type,
    )
    response['Cache-Control'] = 'no-cache'
    return response


urlpatterns = [
    path('manifest.webmanifest', pwa_asset, {'filename': 'manifest.webmanifest', 'content_type': 'application/manifest+json'}, name='pwa-manifest'),
    path('pwa-icon-192.png', pwa_asset, {'filename': 'pwa-icon-192.png', 'content_type': 'image/png'}, name='pwa-icon-192'),
    path('pwa-icon-512.png', pwa_asset, {'filename': 'pwa-icon-512.png', 'content_type': 'image/png'}, name='pwa-icon-512'),
    path('sw.js', service_worker, name='service-worker'),
    path('', never_cache(login_required(TemplateView.as_view(template_name='index.html'))), name='dashboard'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('employee-password/', password_setup_page, name='employee-password-setup'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]
