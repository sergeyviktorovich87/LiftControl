from django.http import FileResponse
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


urlpatterns = [
    path('sw.js', service_worker, name='service-worker'),
    path('', never_cache(login_required(TemplateView.as_view(template_name='index.html'))), name='dashboard'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('employee-password/', password_setup_page, name='employee-password-setup'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]
