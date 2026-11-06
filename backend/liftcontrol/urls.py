from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views.generic import TemplateView
from django.urls import include, path

# Administrative configuration is reserved to superusers. Operational roles use the app.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
urlpatterns = [
    path('', login_required(TemplateView.as_view(template_name='index.html')), name='dashboard'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]
